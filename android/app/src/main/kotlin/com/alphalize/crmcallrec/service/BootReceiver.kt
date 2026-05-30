package com.alphalize.crmcallrec.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Restarts [FileObserverService] after device boot so the watcher resumes
 * before the user opens the app. Requires RECEIVE_BOOT_COMPLETED permission.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i("BootReceiver", "BOOT_COMPLETED — starting FileObserverService")
            FileObserverService.start(context)
        }
    }
}
