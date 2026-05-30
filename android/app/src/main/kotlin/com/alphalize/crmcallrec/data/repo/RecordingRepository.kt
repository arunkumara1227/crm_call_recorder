package com.alphalize.crmcallrec.data.repo

import android.util.Log
import com.alphalize.crmcallrec.data.db.RecordingDao
import com.alphalize.crmcallrec.data.db.RecordingEntity
import com.alphalize.crmcallrec.data.prefs.SecurePrefs
import com.alphalize.crmcallrec.domain.AudioFileFilter
import com.alphalize.crmcallrec.domain.CallLogLookup
import com.alphalize.crmcallrec.domain.FilenamePhoneParser
import com.alphalize.crmcallrec.domain.HashUtil
import com.alphalize.crmcallrec.domain.SimRegistry
import java.io.File
import kotlinx.coroutines.flow.Flow

/**
 * Detects a file, gathers metadata, applies per-SIM filter, dedupes by sha256,
 * persists to Room. Upload itself is the UploadWorker's responsibility.
 */
class RecordingRepository(
    private val dao: RecordingDao,
    private val callLog: CallLogLookup,
    private val sims: SimRegistry,
    private val prefs: SecurePrefs,
) {

    fun observeRecent(limit: Int = 50): Flow<List<RecordingEntity>> = dao.observeRecent(limit)

    fun observeQueuedCount(): Flow<Int> = dao.observeQueuedCount()

    suspend fun listPending(): List<RecordingEntity> =
        dao.listByStatus(RecordingEntity.STATUS_PENDING)

    suspend fun get(id: Long) = dao.get(id)

    /**
     * Idempotent — re-enqueues of the same file content are silent no-ops thanks
     * to the unique sha256 index. Returns the row id, or null if the file was
     * skipped (not audio / pre-install / dup sha / SIM filter rejected).
     *
     * Flow:
     *   1. Reject non-audio + pre-install files cheaply.
     *   2. CallLog lookup (cheap) → derive SIM info.
     *   3. SIM filter — skip BEFORE the expensive SHA-256 hash if not allowed.
     *   4. Hash + dedup against Room.
     *   5. Resolve phone (CallLog → filename → parent folder).
     *   6. Insert with the SIM label populated.
     */
    suspend fun enqueueIfNew(file: File, installEpochMs: Long): Long? {
        if (!AudioFileFilter.isAudio(file)) {
            Log.d(TAG, "Skipping (not audio): ${file.absolutePath}")
            return null
        }
        if (file.lastModified() < installEpochMs) {
            Log.d(TAG, "Skipping (pre-install): ${file.absolutePath}")
            return null
        }

        val mtime = file.lastModified()
        val fromCallLog = callLog.lookupForFile(mtime)
        val sim = fromCallLog?.phoneAccountId?.let { sims.forPhoneAccountId(it) }

        if (!isSimAllowed(sim)) {
            Log.i(TAG, "Skipping (SIM not allowed): subId=${sim?.subscriptionId} label=${sim?.label} for ${file.absolutePath}")
            return null
        }

        val sha = HashUtil.sha256(file)
        val existing = dao.getBySha(sha)
        if (existing != null) {
            Log.d(TAG, "Skipping (dup sha): ${file.absolutePath}")
            return null
        }

        // Phone resolution: CallLog → filename digits → parent folder name.
        val phone = fromCallLog?.phone?.takeIf { it.isNotBlank() }
            ?: FilenamePhoneParser.extract(file.name).takeIf { it.isNotBlank() }
            ?: FilenamePhoneParser.extract(file.parentFile?.name ?: "")
        val direction = fromCallLog?.direction ?: RecordingEntity.DIR_UNKNOWN
        val duration = fromCallLog?.durationSec ?: 0
        val callDate = fromCallLog?.callDateUtcMs ?: mtime

        val rec = RecordingEntity(
            path = file.absolutePath,
            sha256 = sha,
            phone = phone,
            direction = direction,
            durationSec = duration,
            callDateUtcMs = callDate,
            status = RecordingEntity.STATUS_PENDING,
            createdAt = System.currentTimeMillis(),
            simLabel = sim?.label.orEmpty(),
        )
        val rowId = dao.insertIgnoreDuplicate(rec)
        return if (rowId > 0) {
            Log.i(TAG, "Enqueued #$rowId: phone=$phone direction=$direction dur=${duration}s sim=${rec.simLabel} path=${file.absolutePath}")
            rowId
        } else null
    }

    /**
     * Allow-list semantics:
     *   - null pref       → allow any SIM (incl. SIM-unresolved files)
     *   - non-null pref:
     *       - sim resolved AND id in set     → allowed
     *       - sim resolved AND id NOT in set → blocked
     *       - sim unresolved                 → blocked (cautious default —
     *         user has explicitly chosen which SIMs to allow, so we don't
     *         leak unknown-SIM recordings)
     */
    private fun isSimAllowed(sim: com.alphalize.crmcallrec.domain.SimInfo?): Boolean {
        val allowed = prefs.allowedSimSubIds ?: return true
        if (sim == null) return false
        return sim.subscriptionId in allowed
    }

    suspend fun setStatus(id: Long, status: String, error: String? = null) =
        dao.setStatus(id, status, error)

    suspend fun incrementAttempts(id: Long) = dao.incrementAttempts(id)

    suspend fun markDone(id: Long, remoteId: Long?, partnerId: Long?, leadId: Long?) =
        dao.markDone(id, remoteId, partnerId, leadId)

    suspend fun update(rec: RecordingEntity) = dao.update(rec)

    private companion object {
        const val TAG = "RecordingRepository"
    }
}
