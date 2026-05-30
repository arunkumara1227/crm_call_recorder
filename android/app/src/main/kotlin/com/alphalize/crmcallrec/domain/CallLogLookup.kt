package com.alphalize.crmcallrec.domain

import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import android.util.Log
import com.alphalize.crmcallrec.data.db.RecordingEntity

data class CallInfo(
    val phone: String,
    val direction: String,
    val durationSec: Int,
    val callDateUtcMs: Long,
    /** Raw CallLog PHONE_ACCOUNT_ID — used by SimRegistry to resolve which SIM. */
    val phoneAccountId: String?,
)

/**
 * Looks up a call recording's metadata in the system CallLog provider.
 *
 * Strategy: scan rows whose DATE is within ±[windowMs] of the file's mtime,
 * then pick the one whose DATE + DURATION is closest to mtime (i.e. the call
 * that hung up right when the file finished writing).
 *
 * Returns null if READ_CALL_LOG is not granted, the provider is empty,
 * or no row falls inside the window.
 */
class CallLogLookup(private val context: Context) {

    fun lookupForFile(fileMtimeMs: Long, windowMs: Long = 120_000L): CallInfo? {
        if (!hasReadCallLog()) {
            Log.w(TAG, "READ_CALL_LOG not granted — skipping CallLog lookup")
            return null
        }
        val from = fileMtimeMs - windowMs
        val to = fileMtimeMs + windowMs
        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.TYPE,
            CallLog.Calls.DURATION,
            CallLog.Calls.DATE,
            CallLog.Calls.PHONE_ACCOUNT_ID,
        )
        val selection = "${CallLog.Calls.DATE} BETWEEN ? AND ?"
        val args = arrayOf(from.toString(), to.toString())
        val sort = "${CallLog.Calls.DATE} DESC"

        var best: CallInfo? = null
        var bestDistanceMs = Long.MAX_VALUE

        try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI, projection, selection, args, sort,
            )?.use { c ->
                val iNum = c.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
                val iType = c.getColumnIndexOrThrow(CallLog.Calls.TYPE)
                val iDur = c.getColumnIndexOrThrow(CallLog.Calls.DURATION)
                val iDate = c.getColumnIndexOrThrow(CallLog.Calls.DATE)
                val iAcct = c.getColumnIndex(CallLog.Calls.PHONE_ACCOUNT_ID)
                while (c.moveToNext()) {
                    val phone = c.getString(iNum) ?: ""
                    val type = c.getInt(iType)
                    val dur = c.getInt(iDur)
                    val date = c.getLong(iDate)
                    val acct = if (iAcct >= 0) c.getString(iAcct) else null
                    val hangupMs = date + dur * 1000L
                    val distance = kotlin.math.abs(hangupMs - fileMtimeMs)
                    if (distance < bestDistanceMs) {
                        bestDistanceMs = distance
                        best = CallInfo(
                            phone = phone,
                            direction = mapDirection(type),
                            durationSec = dur,
                            callDateUtcMs = date,
                            phoneAccountId = acct,
                        )
                    }
                }
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "SecurityException reading CallLog: ${e.message}")
            return null
        }
        return best
    }

    private fun hasReadCallLog(): Boolean =
        context.checkSelfPermission(android.Manifest.permission.READ_CALL_LOG) ==
            PackageManager.PERMISSION_GRANTED

    private fun mapDirection(callLogType: Int): String = when (callLogType) {
        CallLog.Calls.INCOMING_TYPE -> RecordingEntity.DIR_INCOMING
        CallLog.Calls.OUTGOING_TYPE -> RecordingEntity.DIR_OUTGOING
        else -> RecordingEntity.DIR_UNKNOWN  // MISSED/REJECTED/VOICEMAIL/BLOCKED — usually no audio anyway
    }

    private companion object {
        const val TAG = "CallLogLookup"
    }
}
