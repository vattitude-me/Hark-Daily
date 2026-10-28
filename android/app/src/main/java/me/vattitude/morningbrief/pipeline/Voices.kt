package me.vattitude.morningbrief.pipeline

/**
 * A voice the shared pack records (app/storypack.py). C-3PO serves as the permanent flagship anchor,
 * accompanied by modular neural personas (such as Matthew and Kelly) that listeners can select.
 */
data class PackVoice(
    val id: String,
    val name: String,
    val gender: String,
    val style: String = "",
    val description: String = "",
)

val PACK_VOICES = listOf(
    PackVoice("c3po_reference", "C-3PO", "male", "Polite & Precise", "Polite protocol droid"),
    PackVoice("matthew_reference", "Matthew", "male", "Conversational", "Calm American newsreader"),
    PackVoice("kelly_reference", "Kelly", "female", "Clear & Engaging", "Engaging American newsreader"),
)

/**
 * The voice a listener picked. Matches known pack voices or dynamically synthesizes
 * metadata for any modular narrator ID, falling back to C-3PO when null.
 */
fun packVoice(id: String?): PackVoice {
    if (id == null) return PACK_VOICES.first()
    PACK_VOICES.firstOrNull { it.id == id }?.let { return it }
    val cleanName = id.removeSuffix("_reference")
        .removeSuffix("_american")
        .removeSuffix("_male")
        .removeSuffix("_female")
        .replace('_', ' ')
        .trim()
        .split(' ')
        .filter { it.isNotBlank() }
        .joinToString(" ") { it.replaceFirstChar { c -> c.uppercase() } }
    return PackVoice(id, cleanName.ifEmpty { id }, "neutral", "Broadcast", "Neural narrator")
}

/** Which voice's clips to play: the chosen one, or whichever is actually published. */
internal fun pickPackVoice(published: List<String>, chosen: String?): String? {
    val real = published.filter { it.isNotBlank() }
    if (real.isEmpty()) return null
    if (chosen != null && real.contains(chosen)) return chosen
    return real.groupingBy { it }.eachCount().maxByOrNull { it.value }?.key
}
