package com.alphalize.crmcallrec.domain

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.telephony.SubscriptionManager
import android.util.Log

data class SimInfo(
    /** Stable Android subscription id. Persisted in prefs as the allow-list key. */
    val subscriptionId: Int,
    /** 0-based slot. Useful for the "SIM 1" / "SIM 2" prefix. */
    val slotIndex: Int,
    /** Carrier name from the SIM (e.g. "Jio", "Airtel"). May be blank on some ROMs. */
    val carrierName: String,
    /** User-facing label for the Settings screen and the upload field. */
    val label: String,
)

/**
 * Reads the active SIMs via [SubscriptionManager].
 *
 * Requires `READ_PHONE_STATE` runtime permission on Android 6+.
 * Returns an empty list if permission is missing or the device is single-SIM
 * with no active subscription (very rare on actual phones).
 */
class SimRegistry(private val context: Context) {

    fun listActive(): List<SimInfo> {
        if (!hasPermission()) {
            Log.w(TAG, "READ_PHONE_STATE not granted — returning empty SIM list")
            return emptyList()
        }
        val mgr = context.getSystemService(SubscriptionManager::class.java) ?: return emptyList()
        return try {
            mgr.activeSubscriptionInfoList.orEmpty().map { info ->
                val carrier = info.carrierName?.toString().orEmpty()
                val slot = info.simSlotIndex
                val label = buildString {
                    append("SIM ")
                    append(slot + 1)
                    if (carrier.isNotBlank()) {
                        append(" — ")
                        append(carrier)
                    }
                }
                SimInfo(
                    subscriptionId = info.subscriptionId,
                    slotIndex = slot,
                    carrierName = carrier,
                    label = label,
                )
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "SecurityException reading SIMs: ${e.message}")
            emptyList()
        }
    }

    /**
     * Resolve the SIM info for a CallLog `PHONE_ACCOUNT_ID`. On most modern
     * Android devices the account ID is just the subscription ID as a String,
     * but the value can be opaque or carrier-specific — we try numeric match
     * first, fall back to slot match if the value parses as a small integer.
     */
    fun forPhoneAccountId(phoneAccountId: String?): SimInfo? {
        if (phoneAccountId.isNullOrBlank()) return null
        val all = listActive()
        val asInt = phoneAccountId.toIntOrNull() ?: return all.firstOrNull { sim ->
            sim.label.equals(phoneAccountId, ignoreCase = true)
        }
        // Numeric — match against subscriptionId first, then slot+1.
        return all.firstOrNull { it.subscriptionId == asInt }
            ?: all.firstOrNull { it.slotIndex == asInt - 1 || it.slotIndex == asInt }
    }

    private fun hasPermission(): Boolean =
        context.checkSelfPermission(Manifest.permission.READ_PHONE_STATE) ==
            PackageManager.PERMISSION_GRANTED

    private companion object {
        const val TAG = "SimRegistry"
    }
}
