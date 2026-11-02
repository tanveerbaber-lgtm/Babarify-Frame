plugins {
    id("com.android.application")
}

android {
    namespace = "com.babarify.frame.prototype"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.babarify.frame.prototype"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "0.0.1-prototype"
    }

    // One app per engine, so APK size and merged permissions compare directly.
    flavorDimensions += "engine"
    productFlavors {
        create("media3") {
            dimension = "engine"
            applicationIdSuffix = ".media3"
        }
        create("vlc") {
            dimension = "engine"
            applicationIdSuffix = ".vlc"
        }
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = false
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Prototype only: signed with the debug key so it can be installed for measurement.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    "media3Implementation"("androidx.media3:media3-exoplayer:1.11.1")
    "vlcImplementation"("org.videolan.android:libvlc-all:3.7.7")
}
