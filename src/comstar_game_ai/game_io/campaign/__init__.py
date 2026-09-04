"""Campaign-map actuation: UI mode, modals, orders, end turn."""

from comstar_game_ai.game_io.campaign.end_turn import end_turn_campaign
from comstar_game_ai.game_io.campaign.modal import ModalHandler, ensure_campaign_map
from comstar_game_ai.game_io.campaign.orders import CampaignOrder, CampaignPlanner
from comstar_game_ai.game_io.campaign.ui_mode import CampaignUiMode, UiClassification, classify_campaign_image

__all__ = [
    "CampaignOrder",
    "CampaignPlanner",
    "CampaignUiMode",
    "ModalHandler",
    "UiClassification",
    "classify_campaign_image",
    "end_turn_campaign",
    "ensure_campaign_map",
]
