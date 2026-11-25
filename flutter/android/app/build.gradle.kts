plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Ścieżka do klucza podpisu (ustawia ją .github/workflows/build-apk.yml)
val releaseKeystore: String? = System.getenv("STRATO_KEYSTORE")?.takeIf { it.isNotBlank() }

android {
    namespace = "com.example.stratosteam"
    compileSdk = flutter.compileSdkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.stratosteam"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (releaseKeystore != null) {
            create("stratosteam") {
                storeFile = file(releaseKeystore)
                storeType = "PKCS12"
                storePassword = System.getenv("STRATO_KEYSTORE_PASSWORD")
                keyAlias = "stratosteam"
                keyPassword = System.getenv("STRATO_KEYSTORE_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // Stały podpis z GitHub Actions; lokalnie bez klucza — podpis debug.
            signingConfig = signingConfigs.getByName(if (releaseKeystore != null) "stratosteam" else "debug")
        }
    }
}

flutter {
    source = "../.."
}
