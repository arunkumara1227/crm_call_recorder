package com.alphalize.crmcallrec.ui.settings

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.alphalize.crmcallrec.CrmCallRecApp
import com.alphalize.crmcallrec.domain.SimInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class TestState {
    data object Idle : TestState()
    data object Running : TestState()
    data class Ok(val serverTime: String) : TestState()
    data class Error(val message: String) : TestState()
}

class SettingsViewModel(app: Application) : AndroidViewModel(app) {

    private val locator = (app as CrmCallRecApp).locator
    val config: StateFlow<com.alphalize.crmcallrec.data.prefs.SecurePrefs.Config> = locator.prefs.config

    private val _testState = MutableStateFlow<TestState>(TestState.Idle)
    val testState: StateFlow<TestState> = _testState.asStateFlow()

    private val _sims = MutableStateFlow<List<SimInfo>>(emptyList())
    val sims: StateFlow<List<SimInfo>> = _sims.asStateFlow()

    /** Allow-set; null means "all SIMs allowed" (default). */
    private val _allowedSimIds = MutableStateFlow(locator.prefs.allowedSimSubIds)
    val allowedSimIds: StateFlow<Set<Int>?> = _allowedSimIds.asStateFlow()

    init {
        refreshSims()
    }

    fun refreshSims() {
        _sims.value = locator.sims.listActive()
        // Self-heal: after a SIM hot-swap (eSIM change, dual-SIM mode toggle,
        // region change) the stored allow-list may contain IDs for SIMs that
        // are no longer active. Prune those stale IDs. If the pruned set
        // covers every currently-active SIM, collapse back to null (= the
        // "all allowed" default).
        val activeIds = _sims.value.map { it.subscriptionId }.toSet()
        val current = locator.prefs.allowedSimSubIds
        if (current != null && activeIds.isNotEmpty()) {
            val pruned = current.intersect(activeIds)
            val nextValue: Set<Int>? = if (pruned == activeIds) null else pruned
            if (nextValue != current) {
                locator.prefs.allowedSimSubIds = nextValue
                _allowedSimIds.value = nextValue
            }
        }
    }

    /** UI toggles call this — flip a SIM's allowed/blocked state. */
    fun toggleSimAllowed(subId: Int, allowed: Boolean) {
        val current = _allowedSimIds.value
        val allSubIds = _sims.value.map { it.subscriptionId }.toSet()
        val next: Set<Int>? = when {
            // First toggle from default "all allowed" — materialise the full set then flip.
            current == null -> if (allowed) allSubIds else (allSubIds - subId)
            allowed -> current + subId
            else -> current - subId
        }
        // If user re-enabled everything, collapse back to null (= default).
        val collapsed = if (next != null && next == allSubIds) null else next
        _allowedSimIds.value = collapsed
        locator.prefs.allowedSimSubIds = collapsed
    }

    fun save(serverUrl: String, database: String, apiKey: String) {
        locator.prefs.saveConfig(serverUrl, database, apiKey)
        _testState.value = TestState.Idle
    }

    fun testConnection() {
        viewModelScope.launch {
            _testState.value = TestState.Running
            val api = locator.network.currentApi()
            if (api == null) {
                _testState.value = TestState.Error("Server URL is blank — save it first.")
                return@launch
            }
            try {
                val resp = api.ping()
                val body = resp.body()
                when {
                    resp.code() == 401 -> _testState.value =
                        TestState.Error("401 — bad or missing API key.")
                    resp.code() == 404 -> _testState.value =
                        TestState.Error("404 — wrong database or URL. Check both.")
                    !resp.isSuccessful -> _testState.value =
                        TestState.Error("HTTP ${resp.code()} ${resp.message()}")
                    body == null || !body.ok -> _testState.value =
                        TestState.Error(body?.error ?: "Unknown server response")
                    else -> _testState.value =
                        TestState.Ok(body.server_time ?: "(no timestamp)")
                }
            } catch (e: Exception) {
                _testState.value = TestState.Error(e.message ?: e.javaClass.simpleName)
            }
        }
    }
}
