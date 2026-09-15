"""Label Studio category list for RTW YOLOX (import as labeling config helper).

Paste into Label Studio / CVAT as rectangle labels. Order must match training
class ids 0..3.
"""

LABELS = [
    "settlement_badge",
    "settlement_oval",
    "army_stack",
    "ship",
]

# Label Studio XML snippet
LABEL_STUDIO_XML = """
<View>
  <Image name="image" value="$image"/>
  <RectangleLabels name="label" toName="image">
    <Label value="settlement_badge" background="#ff6b6b"/>
    <Label value="settlement_oval" background="#feca57"/>
    <Label value="army_stack" background="#48dbfb"/>
    <Label value="ship" background="#5f27cd"/>
  </RectangleLabels>
</View>
""".strip()
