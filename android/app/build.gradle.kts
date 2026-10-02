import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Release builds set these from the tag (android-v0.2.0 → 0.2.0); local builds use the defaults.
val appVersionName = (findProperty("versionName") as String?) ?: "0.1.0"
val appVersionCode = (findProperty("versionCode") as String?)?.toInt() ?: 1

android {
    namespace = "me.vattitude.morningbrief"
    compileSdk = 36

    defaultConfig {
        applicationId = "me.vattitude.morningbrief"
        minSdk = 29
        targetSdk = 36
        versionCode = appVersionCode
        versionName = appVersionName
        // Phones only: the Kokoro engine's native libraries are large, so x86 builds are left out.
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    // Compressed native libraries keep the download small; they're unpacked once at install.
    packaging { jniLibs { useLegacyPackaging = true } }

    // The source catalog is shared with the worker: app/catalog/sources.json at the repo root.
    sourceSets["main"].resources.srcDir("../../app/catalog")

    base.archivesName = "morning-brief"

    applicationVariants.all {
        outputs.all {
            val suffix = if (buildType.name == "release") "" else "-${buildType.name}"
            (this as com.android.build.gradle.internal.api.BaseVariantOutputImpl)
                .outputFileName = "morning-brief-$appVersionName$suffix.apk"
        }
    }

    // Signing comes from keystore.properties locally, or from environment variables in CI.
    // Neither is committed; without them the release build is unsigned.
    val signing = Properties().apply {
        rootProject.file("keystore.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
        System.getenv("ANDROID_KEYSTORE")?.let { setProperty("storeFile", it) }
        System.getenv("ANDROID_KEYSTORE_PASSWORD")?.let { setProperty("storePassword", it) }
        System.getenv("ANDROID_KEY_ALIAS")?.let { setProperty("keyAlias", it) }
        System.getenv("ANDROID_KEY_PASSWORD")?.let { setProperty("keyPassword", it) }
    }
    val canSign = signing.getProperty("storeFile") != null
    signingConfigs {
        create("release") {
            if (canSign) {
                storeFile = file(signing.getProperty("storeFile"))
                storePassword = signing.getProperty("storePassword")
                keyAlias = signing.getProperty("keyAlias")
                keyPassword = signing.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (canSign) signingConfig = signingConfigs.getByName("release")
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui-tooling-preview")
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.browser:browser:1.8.0")

    implementation("androidx.work:work-runtime-ktx:2.10.0")
    implementation("androidx.media3:media3-exoplayer:1.5.1")
    implementation("androidx.media3:media3-session:1.5.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-guava:1.8.1")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.jsoup:jsoup:1.18.3")
    implementation("net.dankito.readability4j:readability4j:1.0.8")
    implementation("io.coil-kt:coil-compose:2.7.0")

    // Kokoro neural voices, run on the phone; the voice model itself is an optional download.
    implementation("com.github.k2-fsa.sherpa-onnx:sherpa-onnx:v1.13.8@aar")
    implementation("org.apache.commons:commons-compress:1.27.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
