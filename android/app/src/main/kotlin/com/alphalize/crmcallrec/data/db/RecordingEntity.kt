package com.alphalize.crmcallrec.data.db

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * One row per call recording the watcher has seen. The unique [sha256] index
 * makes re-inserts (e.g. ScanWorker rediscovering a file) a silent no-op.
 *
 * Lifecycle:  pending  →  uploading  →  done | failed
 * `done` carries the Odoo remoteId + matched partner/lead.
 */
@Entity(
    tableName = "recordings",
    indices = [
        Index(value = ["sha256"], unique = true),
        Index(value = ["status"]),
        Index(value = ["createdAt"]),
    ],
)
data class RecordingEntity(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    /** Absolute file path on the device. May change if the user clears caches; we trust sha256. */
    val path: String,
    /** SHA-256 of the file contents — used for dedup across rescans + path renames. */
    val sha256: String,
    /** Phone number extracted from CallLog (preferred) or filename (fallback). May be "". */
    val phone: String,
    /** "incoming" | "outgoing" | "unknown" — server's accepted values. */
    val direction: String,
    val durationSec: Int,
    /** UTC epoch millis of the call (from CallLog DATE or file mtime). */
    val callDateUtcMs: Long,
    /** pending | uploading | done | failed */
    val status: String,
    val remoteId: Long? = null,
    val matchedPartnerId: Long? = null,
    val matchedLeadId: Long? = null,
    val attempts: Int = 0,
    val lastError: String? = null,
    @ColumnInfo(defaultValue = "0")
    val createdAt: Long,
    /** Friendly SIM label (e.g. "SIM 1 — Jio"). Empty when SIM info unavailable. */
    val simLabel: String = "",
) {
    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_UPLOADING = "uploading"
        const val STATUS_DONE = "done"
        const val STATUS_FAILED = "failed"

        const val DIR_INCOMING = "incoming"
        const val DIR_OUTGOING = "outgoing"
        const val DIR_UNKNOWN = "unknown"
    }
}
