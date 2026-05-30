package com.alphalize.crmcallrec.domain

import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

object HashUtil {
    /** Streamed SHA-256 over file bytes. Returns lowercase hex. */
    fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        FileInputStream(file).use { input ->
            val buf = ByteArray(8 * 1024)
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                md.update(buf, 0, n)
            }
        }
        return md.digest().joinToString("") { b -> "%02x".format(b) }
    }
}
