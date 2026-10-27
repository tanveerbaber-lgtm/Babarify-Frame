"""Marshal callbacks from engine/worker threads onto the Qt UI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class UiBridge(QObject):
    """Emit ``post(obj)`` from any thread; ``delivered`` fires on the thread owning this object.

    Qt queues cross-thread signal emissions automatically, so slots connected to
    ``delivered`` always run on the UI thread when the bridge is created there.
    """

    delivered = Signal(object)

    def post(self, payload: object) -> None:
        self.delivered.emit(payload)
