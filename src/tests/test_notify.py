from doc_sync.notify import CallbackNotifier, LoggingNotifier


def test_callback_notifier_delegates():
    delivered = []
    notifier = CallbackNotifier(lambda subject, message: delivered.append((subject, message)))
    notifier.notify("failed", "details")
    assert delivered == [("failed", "details")]


def test_logging_notifier_is_local_adapter(caplog):
    LoggingNotifier().notify("failed", "details")
    assert "Notification required" in caplog.text
