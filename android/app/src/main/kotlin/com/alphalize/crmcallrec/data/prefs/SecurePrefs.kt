package com.alphalize.crmcallrec.data.prefs

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Encrypted prefs for server URL, database, API key, watched folders, install epoch.
 *
 * Exposes a [config] StateFlow so the network layer can rebuild Retrofit when the
 * URL/key changes without needing a process restart. Reads/writes are synchronous —
 * EncryptedSharedPreferences calls are fast on AES-256-GCM and we only touch them
 * on Settings save or app start.
 */
class SecurePrefs(context: Context) {

    private val prefs: SharedPreferences = run {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "crmcallrec_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    data class Config(
        val serverUrl: String,
        val database: String,
        val apiKey: String,
    ) {
        val isComplete: Boolean
            get() = serverUrl.isNotBlank() && apiKey.isNotBlank()
    }

    private val _config = MutableStateFlow(readConfig())
    val config: StateFlow<Config> = _config.asStateFlow()

    private fun readConfig() = Config(
        serverUrl = prefs.getString(KEY_SERVER, "") ?: "",
        database = prefs.getString(KEY_DB, "") ?: "",
        apiKey = prefs.getString(KEY_API_KEY, "") ?: "",
    )

    fun saveConfig(serverUrl: String, database: String, apiKey: String) {
        prefs.edit()
            .putString(KEY_SERVER, serverUrl.trim().trimEnd('/'))
            .putString(KEY_DB, database.trim())
            .putString(KEY_API_KEY, apiKey.trim())
            .apply()
        _config.value = readConfig()
    }

    /** Set on first launch — files older than this are skipped (no backfill). */
    var installEpochMs: Long
        get() = prefs.getLong(KEY_INSTALL_EPOCH, 0L)
        set(value) { prefs.edit().putLong(KEY_INSTALL_EPOCH, value).apply() }

    /**
     * Folders to watch for call recordings. Defaults to the path the user
     * found on their Infinix; user can later expand this via Settings (TBD).
     */
    var watchedFolders: List<String>
        get() {
            val csv = prefs.getString(KEY_WATCHED_FOLDERS, null) ?: DEFAULT_WATCHED_FOLDERS_CSV
            return csv.split('|').filter { it.isNotBlank() }
        }
        set(value) {
            prefs.edit().putString(KEY_WATCHED_FOLDERS, value.joinToString("|")).apply()
        }

    /**
     * Allow-list of subscription IDs for the per-SIM filter. Null = "any SIM
     * goes" (default — equivalent to allowing every SIM, including future ones
     * the user might add). An explicit list means only those IDs are uploaded;
     * empty list means NO SIMs are uploaded (rarely useful but valid).
     */
    var allowedSimSubIds: Set<Int>?
        get() {
            val csv = prefs.getString(KEY_ALLOWED_SIMS, null) ?: return null
            if (csv.isBlank()) return emptySet()
            return csv.split(',').mapNotNull { it.toIntOrNull() }.toSet()
        }
        set(value) {
            if (value == null) {
                prefs.edit().remove(KEY_ALLOWED_SIMS).apply()
            } else {
                prefs.edit().putString(KEY_ALLOWED_SIMS, value.joinToString(",")).apply()
            }
        }

    private companion object {
        const val KEY_SERVER = "server_url"
        const val KEY_DB = "database"
        const val KEY_API_KEY = "api_key"
        const val KEY_INSTALL_EPOCH = "install_epoch_ms"
        const val KEY_WATCHED_FOLDERS = "watched_folders_csv"
        const val KEY_ALLOWED_SIMS = "allowed_sim_sub_ids_csv"

        // Pipe-separated. Infinix XOS default first; rest are common OEM fallbacks.
        const val DEFAULT_WATCHED_FOLDERS_CSV =
            "/storage/emulated/0/Music/PhoneRecord/" +
            "|/storage/emulated/0/Recordings/Call/" +
            "|/storage/emulated/0/Call recordings/" +
            "|/storage/emulated/0/MIUI/sound_recorder/call_rec/"
    }
}
