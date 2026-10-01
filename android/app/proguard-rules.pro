# Readability4J logs through SLF4J, which isn't bundled.
-dontwarn org.slf4j.**
# jsoup's optional re2j regex engine.
-dontwarn com.google.re2j.**
# sherpa-onnx's JNI code reads its config classes' fields by name.
-keep class com.k2fsa.sherpa.onnx.** { *; }
# commons-compress optional codecs (only bzip2 and tar are used).
-dontwarn org.tukaani.xz.**
-dontwarn com.github.luben.zstd.**
-dontwarn org.brotli.dec.**
-dontwarn org.objectweb.asm.**
