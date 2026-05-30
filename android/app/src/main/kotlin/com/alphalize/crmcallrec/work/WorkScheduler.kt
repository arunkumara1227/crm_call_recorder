package com.alphalize.crmcallrec.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import java.util.concurrent.TimeUnit

object WorkScheduler {

    /** One-shot upload of a single row. Uniqueness keyed by row id; KEEP avoids duplicate enqueue. */
    fun enqueueUpload(context: Context, rowId: Long) {
        val req = OneTimeWorkRequestBuilder<UploadWorker>()
            .setInputData(workDataOf(UploadWorker.KEY_ID to rowId))
            .setConstraints(networkConstraints())
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            uploadName(rowId), ExistingWorkPolicy.KEEP, req,
        )
    }

    /** Periodic backstop: walks watched folders, catches files our FileObserver missed. */
    fun schedulePeriodicScan(context: Context) {
        val req = PeriodicWorkRequestBuilder<ScanWorker>(SCAN_INTERVAL_MIN, TimeUnit.MINUTES)
            .setBackoffCriteria(BackoffPolicy.LINEAR, 5, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            SCAN_NAME, ExistingPeriodicWorkPolicy.KEEP, req,
        )
    }

    private fun networkConstraints(): Constraints =
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()

    private fun uploadName(rowId: Long) = "upload-$rowId"

    private const val SCAN_NAME = "scan-folders"
    private const val SCAN_INTERVAL_MIN = 15L
}
