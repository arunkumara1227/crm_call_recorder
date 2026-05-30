package com.alphalize.crmcallrec.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

@Dao
interface RecordingDao {

    /** Returns rowId, or -1 if a row with the same sha256 already exists. */
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertIgnoreDuplicate(rec: RecordingEntity): Long

    @Update
    suspend fun update(rec: RecordingEntity)

    @Query("SELECT * FROM recordings WHERE id = :id")
    suspend fun get(id: Long): RecordingEntity?

    @Query("SELECT * FROM recordings WHERE sha256 = :sha")
    suspend fun getBySha(sha: String): RecordingEntity?

    @Query("SELECT * FROM recordings WHERE status = :status ORDER BY createdAt ASC")
    suspend fun listByStatus(status: String): List<RecordingEntity>

    /** Observable feed for the Status screen. Newest first. */
    @Query("SELECT * FROM recordings ORDER BY createdAt DESC LIMIT :limit")
    fun observeRecent(limit: Int = 50): Flow<List<RecordingEntity>>

    @Query("SELECT COUNT(*) FROM recordings WHERE status IN ('pending', 'uploading')")
    fun observeQueuedCount(): Flow<Int>

    @Query("UPDATE recordings SET status = :status, lastError = :error WHERE id = :id")
    suspend fun setStatus(id: Long, status: String, error: String? = null)

    @Query("UPDATE recordings SET attempts = attempts + 1 WHERE id = :id")
    suspend fun incrementAttempts(id: Long)

    @Query("""
        UPDATE recordings SET
            status = 'done',
            remoteId = :remoteId,
            matchedPartnerId = :partnerId,
            matchedLeadId = :leadId,
            lastError = NULL
        WHERE id = :id
    """)
    suspend fun markDone(id: Long, remoteId: Long?, partnerId: Long?, leadId: Long?)
}
