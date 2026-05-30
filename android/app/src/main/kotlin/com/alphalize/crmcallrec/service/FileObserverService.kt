package com.alphalize.crmcallrec.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.FileObserver
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.alphalize.crmcallrec.CrmCallRecApp
import com.alphalize.crmcallrec.MainActivity
import com.alphalize.crmcallrec.R
import com.alphalize.crmcallrec.data.repo.RecordingRepository
import com.alphalize.crmcallrec.work.WorkScheduler
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Foreground service. For each configured folder, installs a [FileObserver]
 * that fires on CLOSE_WRITE / MOVED_TO. Each event is debounced 5 s then
 * handed to [RecordingRepository.enqueueIfNew].
 *
 * Survives screen-off via the sticky foreground notification. If the OEM
 * kills it under Doze, Phase 2C's ScanWorker will catch up within 15 min.
 */
class FileObserverService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val debounceHandler = Handler(Looper.getMainLooper())
    private val observers = mutableListOf<FileObserver>()
    private lateinit var repo: RecordingRepository
    private var installEpoch: Long = 0L

    override fun onCreate() {
        super.onCreate()
        val locator = (application as CrmCallRecApp).locator
        repo = locator.repo
        installEpoch = locator.prefs.installEpochMs
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()
        startWatching()
        return START_STICKY
    }

    override fun onDestroy() {
        observers.forEach { it.stopWatching() }
        observers.clear()
        scope.coroutineContext[Job]?.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?) = null

    private fun startInForeground() {
        ensureChannel()
        val tapIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        }
        val tapPI = PendingIntent.getActivity(
            this, 0, tapIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_phone_call)
            .setContentTitle(getString(R.string.notif_watching_title))
            .setContentText(getString(R.string.notif_watching_text))
            .setOngoing(true)
            .setContentIntent(tapPI)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIF_ID, notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val mgr = getSystemService(NotificationManager::class.java)
            if (mgr.getNotificationChannel(CHANNEL_ID) == null) {
                val ch = NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.notif_channel_watcher),
                    NotificationManager.IMPORTANCE_LOW,
                ).apply {
                    description = getString(R.string.notif_channel_watcher_desc)
                    setShowBadge(false)
                }
                mgr.createNotificationChannel(ch)
            }
        }
    }

    private fun startWatching() {
        val locator = (application as CrmCallRecApp).locator
        val folders = locator.prefs.watchedFolders
        Log.i(TAG, "Starting watch on root folders: $folders")
        folders.forEach { path ->
            val root = File(path)
            if (!root.isDirectory) {
                Log.w(TAG, "Folder missing/inaccessible: $path")
                return@forEach
            }
            // Watch the root for both file events AND new subfolder creation
            // (Infinix XOS creates a per-number subfolder for each call.)
            attachObserver(root, watchCreate = true)
            // And watch every existing subfolder for file events.
            root.listFiles { f -> f.isDirectory }?.forEach { sub ->
                attachObserver(sub, watchCreate = false)
            }
        }
    }

    private fun attachObserver(dir: File, watchCreate: Boolean) {
        val mask = if (watchCreate) MASK_WITH_CREATE else MASK
        val obs = makeObserver(dir, mask)
        obs.startWatching()
        observers += obs
        Log.i(TAG, "Watching ${dir.absolutePath} (createEvents=$watchCreate)")
    }

    private fun makeObserver(dir: File, mask: Int): FileObserver {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            object : FileObserver(dir, mask) {
                override fun onEvent(event: Int, path: String?) =
                    handleEvent(dir, event, path)
            }
        } else {
            @Suppress("DEPRECATION")
            object : FileObserver(dir.absolutePath, mask) {
                override fun onEvent(event: Int, path: String?) =
                    handleEvent(dir, event, path)
            }
        }
    }

    private fun handleEvent(dir: File, event: Int, name: String?) {
        if (name.isNullOrBlank()) return
        val target = File(dir, name)

        // CREATE on a directory entry → new per-number subfolder → start watching it,
        // and rescan it now in case a file landed inside before our observer attached.
        if ((event and FileObserver.CREATE) != 0 && target.isDirectory) {
            attachObserver(target, watchCreate = false)
            target.listFiles()?.forEach { existing -> debounceEnqueue(existing) }
            return
        }

        debounceEnqueue(target)
    }

    private fun debounceEnqueue(file: File) {
        debounceHandler.removeCallbacksAndMessages(file.absolutePath)
        debounceHandler.postAtTime(
            { scope.launch { enqueueSettled(file) } },
            /* token = */ file.absolutePath,
            android.os.SystemClock.uptimeMillis() + DEBOUNCE_MS,
        )
    }

    private suspend fun enqueueSettled(file: File) {
        try {
            // Block IO thread — AudioFileFilter.isSettled sleeps 5s by design.
            if (!com.alphalize.crmcallrec.domain.AudioFileFilter.isAudio(file)) return
            if (!com.alphalize.crmcallrec.domain.AudioFileFilter.isSettled(file)) {
                Log.d(TAG, "Not settled after 5s — will get next event: ${file.name}")
                return
            }
            val rowId = repo.enqueueIfNew(file, installEpoch)
            if (rowId != null) {
                WorkScheduler.enqueueUpload(applicationContext, rowId)
            }
        } catch (t: Throwable) {
            Log.e(TAG, "enqueueSettled failed for ${file.absolutePath}", t)
        }
    }

    companion object {
        const val CHANNEL_ID = "crmcallrec_watcher"
        const val NOTIF_ID = 1001
        const val DEBOUNCE_MS = 5_000L
        const val MASK = FileObserver.CLOSE_WRITE or FileObserver.MOVED_TO
        const val MASK_WITH_CREATE = MASK or FileObserver.CREATE
        private const val TAG = "FileObserverService"

        fun start(context: Context) {
            val intent = Intent(context, FileObserverService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
