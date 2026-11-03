plugins {
    id("com.android.application")
}

android {
    namespace = "com.babarify.frame"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.babarify.frame"
        minSdk = 29 // Android 10 (owner decision, M13)
        targetSdk = 37
        versionCode = 2
        versionName = "0.2.0-beta"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    // Per-architecture APKs, so nobody downloads libVLC for a phone type they don't have.
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = false
        }
    }

    // The key is never in the repository; without these properties the release APK is unsigned.
    val keystore = providers.gradleProperty("babarify.keystore").orNull
    signingConfigs {
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = providers.gradleProperty("babarify.keystore.password").get()
                keyAlias = providers.gradleProperty("babarify.key.alias").get()
                keyPassword = providers.gradleProperty("babarify.key.password").get()
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (keystore != null) signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("org.videolan.android:libvlc-all:3.7.7")

    testImplementation("junit:junit:4.13.2")

    androidTestImplementation("androidx.test:core:1.7.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test:rules:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
}
