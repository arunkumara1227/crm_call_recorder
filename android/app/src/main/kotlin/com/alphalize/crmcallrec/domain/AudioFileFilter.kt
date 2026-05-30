package com.alphalize.crmcallrec.domain

import java.io.File

object AudioFileFilter {
    private val ALLOWED_EXTENSIONS = setOf("m4a", "mp3", "opus", "amr", "wav", "aac", "ogg")
    private const val MIN_SIZE_BYTES = 2 * 1024L

    fun isAudio(file: File): Boolean {
        if (!file.isFile) return false
        val ext = file.extension.lowercase()
        if (ext !in ALLOWED_EXTENSIONS) return false
        if (file.length() < MIN_SIZE_BYTES) return false
        return true
    }

    /**
     * Returns true if the file size + mtime haven't moved in [windowMs].
     * Call this after the FileObserver debounce to be sure the recorder finished writing.
     */
    fun isSettled(file: File, windowMs: Long = 5_000L): Boolean {
        if (!file.isFile) return false
        val sizeStart = file.length()
        val mtimeStart = file.lastModified()
        Thread.sleep(windowMs)
        if (!file.isFile) return false
        return file.length() == sizeStart && file.lastModified() == mtimeStart
    }
}
