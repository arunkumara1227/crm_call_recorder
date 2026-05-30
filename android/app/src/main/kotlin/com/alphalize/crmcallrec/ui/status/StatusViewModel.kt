package com.alphalize.crmcallrec.ui.status

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import com.alphalize.crmcallrec.CrmCallRecApp
import com.alphalize.crmcallrec.data.db.RecordingEntity
import kotlinx.coroutines.flow.Flow

class StatusViewModel(app: Application) : AndroidViewModel(app) {
    private val locator = (app as CrmCallRecApp).locator

    val recent: Flow<List<RecordingEntity>> = locator.repo.observeRecent(50)
    val queuedCount: Flow<Int> = locator.repo.observeQueuedCount()
}
