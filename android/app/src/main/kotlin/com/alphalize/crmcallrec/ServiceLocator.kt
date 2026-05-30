package com.alphalize.crmcallrec

import android.content.Context
import com.alphalize.crmcallrec.data.db.AppDatabase
import com.alphalize.crmcallrec.data.net.NetworkModule
import com.alphalize.crmcallrec.data.prefs.SecurePrefs
import com.alphalize.crmcallrec.data.repo.RecordingRepository
import com.alphalize.crmcallrec.domain.CallLogLookup
import com.alphalize.crmcallrec.domain.SimRegistry

/**
 * Tiny manual DI container — held by [CrmCallRecApp] and read by ViewModels via
 * `(application as CrmCallRecApp).locator`. Avoids Hilt/kapt entirely, which keeps
 * builds fast and the source tree small for a sideload-only app.
 */
class ServiceLocator(appContext: Context) {
    val prefs: SecurePrefs = SecurePrefs(appContext)
    val network: NetworkModule = NetworkModule(prefs)
    val db: AppDatabase = AppDatabase.build(appContext)
    val callLog: CallLogLookup = CallLogLookup(appContext)
    val sims: SimRegistry = SimRegistry(appContext)
    val repo: RecordingRepository = RecordingRepository(db.recordingDao(), callLog, sims, prefs)
}
