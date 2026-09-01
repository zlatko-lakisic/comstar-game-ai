from comstar_game_ai.game_io.battle.orders import OrderIssuer, charge, hold_position, move_to_orientation


def test_order_issuer_queues():
    seen: list[str] = []

    issuer = OrderIssuer(on_order=lambda o: seen.append(o.action) or True)
    assert issuer.issue(hold_position((0, 0, 1)))
    assert issuer.issue_many([charge((0, 0, 2)), move_to_orientation((0, 0, 3), x=1, y=2, facing_deg=90)])
    assert seen == ["hold_position", "charge", "move_to_orientation"]
    assert len(issuer.pending) == 3
    issuer.clear()
    assert issuer.pending == []
