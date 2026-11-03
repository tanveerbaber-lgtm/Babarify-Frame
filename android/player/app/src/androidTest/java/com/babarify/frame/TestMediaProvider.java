package com.babarify.frame;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.List;

/**
 * Serves this test package's media assets as {@code content:} addresses, and as a small folder tree
 * in the same address form Android's document providers use.
 *
 * <p>Java on purpose: Android runs this provider in the test package's own process, where the
 * Kotlin runtime is not available (it lives in the app under test).
 */
public final class TestMediaProvider extends ContentProvider {
    public static final String MISSING = "missing.mp4";
    public static final String AUTHORITY = "com.babarify.frame.test.media";
    public static final String TREE_ROOT = "root";
    private static final String SUBFOLDER = "sub";
    private static final String[] ROOT_FILES = {
        "long_60s.mp4", "c_audio_aac.m4a", "not_media.mp4", "s_ext.srt", ".hidden.mp4",
    };
    private static final String[] SUBFOLDER_FILES = {"s_sidecar_720p.mp4"};

    public static Uri uri(String name) {
        return Uri.parse("content://" + AUTHORITY + "/" + name);
    }

    public static Uri tree() {
        return DocumentsContract.buildTreeDocumentUri(AUTHORITY, TREE_ROOT);
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
        List<String> segments = uri.getPathSegments();
        if (segments.size() > 0 && "children".equals(segments.get(segments.size() - 1))) {
            return children(segments.get(segments.size() - 2), projection);
        }
        MatrixCursor cursor = new MatrixCursor(new String[] {OpenableColumns.DISPLAY_NAME});
        String last = uri.getLastPathSegment();
        cursor.addRow(new Object[] {TREE_ROOT.equals(last) ? "Test folder" : last});
        return cursor;
    }

    private Cursor children(String directory, String[] projection) {
        MatrixCursor cursor = new MatrixCursor(projection);
        if (TREE_ROOT.equals(directory)) {
            for (String name : ROOT_FILES) {
                addRow(cursor, projection, name, "application/octet-stream");
            }
            addRow(cursor, projection, SUBFOLDER, DocumentsContract.Document.MIME_TYPE_DIR);
        } else if (SUBFOLDER.equals(directory)) {
            for (String name : SUBFOLDER_FILES) {
                addRow(cursor, projection, name, "application/octet-stream");
            }
        }
        return cursor;
    }

    private void addRow(MatrixCursor cursor, String[] projection, String name, String mime) {
        Object[] row = new Object[projection.length];
        for (int i = 0; i < projection.length; i++) {
            switch (projection[i]) {
                case DocumentsContract.Document.COLUMN_DOCUMENT_ID:
                case DocumentsContract.Document.COLUMN_DISPLAY_NAME:
                    row[i] = name;
                    break;
                case DocumentsContract.Document.COLUMN_MIME_TYPE:
                    row[i] = mime;
                    break;
                case DocumentsContract.Document.COLUMN_SIZE:
                    row[i] = 1000L;
                    break;
                case DocumentsContract.Document.COLUMN_LAST_MODIFIED:
                    row[i] = 1L;
                    break;
                default:
                    row[i] = null;
            }
        }
        cursor.addRow(row);
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
