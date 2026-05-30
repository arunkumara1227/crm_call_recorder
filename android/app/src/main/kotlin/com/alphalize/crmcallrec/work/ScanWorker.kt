package com.alphalize.crmcallrec.work

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.alphalize.crmcallrec.CrmCallRecApp
import com.alphalize.crmcallrec.data.db.RecordingEntity
import com.alphalize.crmcallrec.domain.AudioFileFilter
import java.io.File

/**
 * Backstop: every ~15 min, walk each configured root folder + its first-level
 * subfolders for audio files. Anything new gets enqueued via the repo (sha256
 * dedup) and then handed to [UploadWorker]. Anything already pending in the
 * DB is re-enqueued for upload too — covers the case where a previous
 * UploadWorker died terminally and we want to give it another chance later.
 *
 * Intentionally simple: no recursion past one level, no fancy traversal.
 * Infinix XOS has at most a `<root>/<number>/` two-level structure for now.
 */
class ScanWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    private val locator = (appContext as CrmCallRecApp).locator

    override suspend fun doWork(): Result {
        val installEpoch = locator.prefs.installEpochMs
        val folders = locator.prefs.watchedFolders
        Log.i(TAG, "ScanWorker tick over: $folders")

        var added = 0
        for (path in folders) {
            val root = File(path)
            if (!root.isDirectory) continue
            added += scanDir(root, installEpoch)
            root.listFiles { f -> f.isDirectory }?.forEach { sub ->
                added += scanDir(sub, installEpoch)
            }
        }

        // Also re-trigger upload for anything still pending (terminal-failures stay 'failed' and are ignored).
        val pending = locator.repo.listPending()
        for (rec in pending) {
            WorkScheduler.enqueueUpload(applicationContext, rec.id)
        }
        Log.i(TAG, "ScanWorker done — new=$added, re-uploaded=${pending.size}")
        return Result.success()
    }

    private suspend fun scanDir(dir: File, installEpoch: Long): Int {
        var added = 0
        dir.listFiles { f -> f.isFile && AudioFileFilter.isAudio(f) }?.forEach { audio ->
            val rowId = locator.repo.enqueueIfNew(audio, installEpoch)
            if (rowId != null) {
                WorkScheduler.enqueueUpload(applicationContext, rowId)
                added++
            }
        }
        return added
    }

    companion object {
        private const val TAG = "ScanWorker"
    }
}
