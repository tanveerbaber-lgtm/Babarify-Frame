package com.babarify.frame;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * Serves this test package's media assets as {@code content:} addresses.
 *
 * <p>Java on purpose: Android runs this provider in the test package's own process, where the
 * Kotlin runtime is not available (it lives in the app under test).
 */
public final class TestMediaProvider extends ContentProvider {
    public static final String MISSING = "missing.mp4";

    public static Uri uri(String name) {
        return Uri.parse("content://com.babarify.frame.test.media/" + name);
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        String name = uri.getLastPathSegment();
        if (name == null || name.equals(MISSING)) {
            throw new FileNotFoundException(String.valueOf(name));
        }
        File copy = new File(getContext().getCacheDir(), name);
        if (!copy.exists()) {
            try (InputStream input = getContext().getAssets().open("media/" + name);
                    FileOutputStream output = new FileOutputStream(copy)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = input.read(buffer)) > 0) {
                    output.write(buffer, 0, count);
                }
            } catch (IOException e) {
                throw new FileNotFoundException(name);
            }
        }
        return ParcelFileDescriptor.open(copy, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        MatrixCursor cursor = new MatrixCursor(new String[] {OpenableColumns.DISPLAY_NAME});
        cursor.addRow(new Object[] {uri.getLastPathSegment()});
        return cursor;
    }

    @Override
    public String getType(Uri uri) {
        return null;
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        return null;
    }

    @Override
    public int delete(Uri uri, String selection, String[] args) {
        return 0;
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] args) {
        return 0;
    }
}
