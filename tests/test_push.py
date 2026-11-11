from py_vapid import Vapid

from app import push


def test_stored_vapid_key_is_usable_for_signing(cfg, monkeypatch):
    """pywebpush must receive a parsed key; a raw PEM string fails with 'Could not deserialize key data'."""
    seen = {}

    def fake_webpush(**kw):
        seen["claims"] = kw["vapid_private_key"].sign({**kw["vapid_claims"], "aud": "https://push.example", "exp": 4102444800})

    monkeypatch.setattr(push, "webpush", fake_webpush)
    sent, gone = push.send(cfg, [{"endpoint": "https://fcm.googleapis.com/fcm/send/x", "p256dh": "k", "auth": "a"}], "t", "b")
    assert (sent, gone) == (1, []) and "Authorization" in seen["claims"]


def test_untrusted_push_endpoints_are_rejected(cfg, monkeypatch):
    called = []
    monkeypatch.setattr(push, "webpush", lambda **kw: called.append(kw))

    untrusted = [
        {"endpoint": "https://push.example/x", "p256dh": "k", "auth": "a"},
        {"endpoint": "https://10.0.0.1:8080/hook", "p256dh": "k", "auth": "a"},
        {"endpoint": "http://fcm.googleapis.com/fcm/send/x", "p256dh": "k", "auth": "a"},  # Not HTTPS
        {"endpoint": "https://evil-push.com/notify", "p256dh": "k", "auth": "a"},
    ]
    sent, gone = push.send(cfg, untrusted, "t", "b")
    assert sent == 0
    assert len(called) == 0
