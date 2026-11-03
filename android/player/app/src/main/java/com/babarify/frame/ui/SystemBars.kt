package com.babarify.frame.ui

import android.os.Build
import android.view.View
import android.view.WindowInsets

/**
 * Android 15+ draws apps under the system bars, so every screen must keep its controls clear of
 * them (M12: the prototype's buttons sat under the navigation bar).
 */
fun applySystemBarPadding(view: View, includeTop: Boolean = true) {
    view.setOnApplyWindowInsetsListener { target, insets ->
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
            target.setPadding(bars.left, if (includeTop) bars.top else 0, bars.right, bars.bottom)
        } else {
            // Android 10 does not draw apps under the bars unless asked; this keeps it correct anyway.
            @Suppress("DEPRECATION")
            target.setPadding(
                insets.systemWindowInsetLeft,
                if (includeTop) insets.systemWindowInsetTop else 0,
                insets.systemWindowInsetRight,
                insets.systemWindowInsetBottom,
            )
        }
        insets
    }
    view.requestApplyInsets()
}
