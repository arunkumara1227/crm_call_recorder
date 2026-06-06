package com.alphalize.crmcallrec.work

import android.content.Context
import android.util.Log
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.alphalize.crmcallrec.CrmCallRecApp
import com.alphalize.crmcallrec.data.db.RecordingEntity
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Uploads ONE recording row to Odoo's `/crm_call_recorder/upload` endpoint.
 * Lifecycle:
 *   pending  → setStatus(uploading)  → POST  →  markDone(remoteId, matched_*) | retry | failed
 *
 * Retry policy: WorkManager handles exponential backoff (configured in [WorkScheduler]).
 * 4xx → terminal failure (no retry — bad auth/data won't fix itself).
 * 5xx / IOException → Result.retry() (network or server hiccup, try again).
 * Max [MAX_ATTEMPTS] attempts before terminal failure.
 */
class UploadWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {

    private val locator = (appContext as CrmCallRecApp).locator
    private val repo = locator.repo
    private val network = locator.network

    override suspend fun doWork(): Result {
        val id = inputData.getLong(KEY_ID, -1L)
        if (id == -1L) {
            Log.w(TAG, "Missing $KEY_ID input")
            return Result.failure()
        }

        val rec = repo.get(id) ?: run {
            Log.w(TAG, "Row $id gone — nothing to do")
            return Result.success()
        }
        if (rec.status == RecordingEntity.STATUS_DONE) {
            return Result.success()
        }
        if (runAttemptCount >= MAX_ATTEMPTS) {
            Log.w(TAG, "Row $id: max attempts ($MAX_ATTEMPTS) exceeded")
            repo.setStatus(id, RecordingEntity.STATUS_FAILED, "Max retries exceeded")
            return Result.failure()
        }

        val file = File(rec.path)
        if (!file.isFile) {
            repo.setStatus(id, RecordingEntity.STATUS_FAILED, "File missing: ${rec.path}")
            return Result.failure()
        }

        val api = network.currentApi()
        if (api == null) {
            repo.setStatus(id, RecordingEntity.STATUS_FAILED, "Server URL not configured")
            return Result.failure()
        }

        repo.incrementAttempts(id)
        repo.setStatus(id, RecordingEntity.STATUS_UPLOADING)

        val callDateStr = formatUtc(rec.callDateUtcMs)
        val phoneMasked = if (rec.phone.length >= 4) "***" + rec.phone.takeLast(4) else "***"
        Log.i(TAG, "Row $id: POST phone=$phoneMasked dir=${rec.direction} dur=${rec.durationSec}s date=$callDateStr")

        return try {
            val resp = api.upload(
                phone = rec.phone.toRequestBody(TEXT),
                direction = rec.direction.toRequestBody(TEXT),
                duration = rec.durationSec.toString().toRequestBody(TEXT),
                callDate = callDateStr.toRequestBody(TEXT),
                sim = rec.simLabel.toRequestBody(TEXT),
                file = MultipartBody.Part.createFormData(
                    "file", file.name, file.asRequestBody(mimeFor(file).toMediaType()),
                ),
            )
            val body = resp.body()
            val code = resp.code()

            when {
                resp.isSuccessful && body?.ok == true -> {
                    repo.markDone(
                        id = id,
                        remoteId = body.id,
                        partnerId = body.matched_partner_id,
                        leadId = body.matched_lead_id,
                    )
                    Log.i(TAG, "Row $id: done remoteId=${body.id} state=${body.state} partner=${body.matched_partner_id} lead=${body.matched_lead_id}")
                    Result.success()
                }
                code in 400..499 -> {
                    // Bad auth/input — won't recover, don't waste retries.
                    val err = "HTTP $code: ${body?.error ?: resp.message()}"
                    Log.w(TAG, "Row $id: terminal failure: $err")
                    repo.setStatus(id, RecordingEntity.STATUS_FAILED, err)
                    Result.failure()
                }
                else -> {
                    // 5xx — server-side, retry with backoff.
                    val err = "HTTP $code: ${body?.error ?: resp.message()} (will retry)"
                    Log.w(TAG, "Row $id: $err")
                    repo.setStatus(id, RecordingEntity.STATUS_PENDING, err)
                    Result.retry()
                }
            }
        } catch (e: IOException) {
            val err = "Network: ${e.message ?: e.javaClass.simpleName} (will retry)"
            Log.w(TAG, "Row $id: $err")
            repo.setStatus(id, RecordingEntity.STATUS_PENDING, err)
            Result.retry()
        } catch (e: Exception) {
            val err = e.message ?: e.javaClass.simpleName
            Log.e(TAG, "Row $id: terminal: $err", e)
            repo.setStatus(id, RecordingEntity.STATUS_FAILED, err)
            Result.failure()
        }
    }

    private fun mimeFor(file: File): String = when (file.extension.lowercase()) {
        "m4a", "mp4" -> "audio/mp4"
        "mp3" -> "audio/mpeg"
        "aac" -> "audio/aac"
        "wav" -> "audio/wav"
        "amr" -> "audio/amr"
        "opus" -> "audio/opus"
        "ogg" -> "audio/ogg"
        else -> "application/octet-stream"
    }

    companion object {
        const val KEY_ID = "id"
        const val MAX_ATTEMPTS = 10
        private const val TAG = "UploadWorker"
        private val TEXT = "text/plain".toMediaType()

        private val UTC_FMT = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }

        private fun formatUtc(epochMs: Long): String = UTC_FMT.format(Date(epochMs))
    }
}
