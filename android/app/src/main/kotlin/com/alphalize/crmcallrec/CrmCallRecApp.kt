package com.alphalize.crmcallrec

import android.app.Application
import com.alphalize.crmcallrec.work.WorkScheduler

class CrmCallRecApp : Application() {

    lateinit var locator: ServiceLocator
        private set

    override fun onCreate() {
        super.onCreate()
        locator = ServiceLocator(applicationContext)

        // Stamp install epoch on first launch so the watcher skips recordings
        // that already existed when the app was installed.
        if (locator.prefs.installEpochMs == 0L) {
            locator.prefs.installEpochMs = System.currentTimeMillis()
        }

        // Periodic backstop — catches files our FileObserver missed (Doze, OEM kill).
        WorkScheduler.schedulePeriodicScan(applicationContext)
    }
}
