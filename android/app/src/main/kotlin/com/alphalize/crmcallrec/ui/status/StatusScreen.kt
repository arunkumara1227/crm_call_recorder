package com.alphalize.crmcallrec.ui.status

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.alphalize.crmcallrec.R
import com.alphalize.crmcallrec.data.db.RecordingEntity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun StatusScreen(vm: StatusViewModel = viewModel()) {
    val recent by vm.recent.collectAsState(initial = emptyList())
    val queued by vm.queuedCount.collectAsState(initial = 0)

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        Text(stringResource(R.string.status_title), style = MaterialTheme.typography.headlineSmall)
        if (queued > 0) {
            Text("$queued in queue", style = MaterialTheme.typography.labelMedium)
        }
        HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))

        if (recent.isEmpty()) {
            Column(
                modifier = Modifier.fillMaxSize(),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Text(stringResource(R.string.status_empty), style = MaterialTheme.typography.bodyMedium)
            }
        } else {
            LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                items(recent, key = { it.id }) { rec -> RecordingRow(rec) }
            }
        }
    }
}

@Composable
private fun RecordingRow(rec: RecordingEntity) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = rec.phone.ifBlank { "(no number)" },
                    style = MaterialTheme.typography.titleMedium,
                )
                StatusChip(rec.status)
            }
            Text(
                text = "${rec.direction} · ${rec.durationSec}s · ${formatTs(rec.callDateUtcMs)}",
                style = MaterialTheme.typography.bodySmall,
            )
            if (rec.status == RecordingEntity.STATUS_DONE && rec.matchedPartnerId != null) {
                Text(
                    text = "Matched contact id=${rec.matchedPartnerId}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            if (rec.lastError != null) {
                Text(
                    text = rec.lastError,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }
}

@Composable
private fun StatusChip(status: String) {
    val (label, bg) = when (status) {
        RecordingEntity.STATUS_PENDING -> stringResource(R.string.status_state_pending) to Color(0xFFFFA000)
        RecordingEntity.STATUS_UPLOADING -> stringResource(R.string.status_state_uploading) to Color(0xFF1976D2)
        RecordingEntity.STATUS_DONE -> stringResource(R.string.status_state_done) to Color(0xFF388E3C)
        RecordingEntity.STATUS_FAILED -> stringResource(R.string.status_state_failed) to Color(0xFFD32F2F)
        else -> status to Color.Gray
    }
    Text(
        text = label,
        modifier = Modifier
            .background(bg, MaterialTheme.shapes.small)
            .padding(horizontal = 8.dp, vertical = 2.dp),
        color = Color.White,
        style = MaterialTheme.typography.labelSmall,
    )
}

private val TS_FMT = SimpleDateFormat("MMM d, HH:mm", Locale.getDefault())
private fun formatTs(ms: Long): String = TS_FMT.format(Date(ms))
