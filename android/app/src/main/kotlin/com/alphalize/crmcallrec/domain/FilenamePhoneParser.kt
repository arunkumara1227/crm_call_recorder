package com.alphalize.crmcallrec.domain

object FilenamePhoneParser {
    private val PHONE_REGEX = Regex("""(\+?\d{7,15})""")

    /**
     * Many OEM recorders embed the phone number in the filename, e.g.
     *   "Call_20260530_120000_+919876543210.m4a"
     *   "98765 43210 outgoing.amr"
     *
     * We extract the LONGEST digit run that's 7-15 digits long. Returns "" if none.
     */
    fun extract(filename: String): String {
        val matches = PHONE_REGEX.findAll(filename).map { it.value }.toList()
        return matches.maxByOrNull { it.length } ?: ""
    }
}
