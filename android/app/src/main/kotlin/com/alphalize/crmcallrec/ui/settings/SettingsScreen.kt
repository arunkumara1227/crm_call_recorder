package com.alphalize.crmcallrec.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.compose.foundation.text.KeyboardOptions
import com.alphalize.crmcallrec.R

@Composable
fun SettingsScreen(vm: SettingsViewModel = viewModel()) {
    val config by vm.config.collectAsState()
    val testState by vm.testState.collectAsState()
    val sims by vm.sims.collectAsState()
    val allowed by vm.allowedSimIds.collectAsState()

    // Re-read SIMs every time the screen comes into focus
    // (covers the case where the user just granted READ_PHONE_STATE).
    LaunchedEffect(Unit) { vm.refreshSims() }

    var server by remember(config.serverUrl) { mutableStateOf(config.serverUrl) }
    var db by remember(config.database) { mutableStateOf(config.database) }
    var key by remember(config.apiKey) { mutableStateOf(config.apiKey) }

    // Sync local fields when prefs change externally.
    LaunchedEffect(config) {
        server = config.serverUrl
        db = config.database
        key = config.apiKey
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(stringResource(R.string.settings_title),
            style = MaterialTheme.typography.headlineSmall)

        OutlinedTextField(
            value = server,
            onValueChange = { server = it },
            label = { Text(stringResource(R.string.settings_server)) },
            placeholder = { Text("http://192.168.1.10:8069") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = db,
            onValueChange = { db = it },
            label = { Text(stringResource(R.string.settings_database)) },
            placeholder = { Text("test9") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = key,
            onValueChange = { key = it },
            label = { Text(stringResource(R.string.settings_api_key)) },
            singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None),
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Button(
                onClick = { vm.save(server, db, key) },
                enabled = server.isNotBlank() && key.isNotBlank(),
            ) { Text(stringResource(R.string.settings_save)) }

            OutlinedButton(
                onClick = { vm.testConnection() },
                enabled = config.isComplete && testState !is TestState.Running,
            ) { Text(stringResource(R.string.settings_test)) }
        }

        when (val s = testState) {
            TestState.Idle -> Unit
            TestState.Running -> Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                CircularProgressIndicator(strokeWidth = 2.dp)
                Text("Testing…")
            }
            is TestState.Ok -> Text(
                "✓ Connected · server_time=${s.serverTime}",
                color = MaterialTheme.colorScheme.primary,
            )
            is TestState.Error -> Text(
                "✗ ${s.message}",
                color = MaterialTheme.colorScheme.error,
            )
        }

        Spacer(Modifier.height(16.dp))
        HorizontalDivider()
        Spacer(Modifier.height(8.dp))

        Text(
            stringResource(R.string.settings_sim_section),
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            stringResource(R.string.settings_sim_hint),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (sims.isEmpty()) {
            Text(
                stringResource(R.string.settings_sim_none),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        } else {
            if (allowed == null) {
                Text(
                    stringResource(R.string.settings_sim_all_allowed),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            sims.forEach { sim ->
                val isAllowed = allowed?.contains(sim.subscriptionId) ?: true
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                ) {
                    Text(sim.label, style = MaterialTheme.typography.bodyLarge)
                    Switch(
                        checked = isAllowed,
                        onCheckedChange = { vm.toggleSimAllowed(sim.subscriptionId, it) },
                    )
                }
            }
        }
    }
}
