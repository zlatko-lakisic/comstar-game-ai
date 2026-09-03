# Hero image prompt for Gemini

The image has one job: hold the project's central tension in a single frame. A warm, dirty, physical ancient battlefield, and a cool, weightless, precise machine layer reading it. The two must not blend into each other, because the whole project is about keeping them separate.

## The prompt

> A wide cinematic aerial three-quarter view of a Roman legion in battle formation on a dry grass plain in late afternoon light. Six cohorts of legionaries stand in tight rectangular blocks, shields raised, their shadows stretching long to the left. Two hundred metres ahead, an enemy line in looser, more ragged formation, its left flank hanging unsupported and exposed. A wedge of Roman cavalry waits on the right, angled to move. Fine ochre dust hangs in the air between the two lines and catches the low sun. The palette is sun-bleached: dry olive and straw grass, oxidised bronze, dulled crimson cloaks, warm grey shields, deep umber shadow.
>
> Overlaid on this scene, and clearly separate from it, is a thin diagrammatic layer in pale cyan, as though a machine were annotating the battlefield in real time. It consists of: hairline one-pixel rectangles bounding each formation, drawn flat with no perspective and no glow; a single dashed arc curving from the cavalry wedge around to the enemy's exposed left flank; one small hollow circle marking a point on the ground at the end of that arc; and four short monospaced numeric labels sitting beside individual units, small enough to read as data rather than as titling. Nothing in this layer casts light, throws shadow, or interacts with the dust.
>
> Style: painterly photographic realism for the battlefield, technical drawing precision for the overlay. The world is textured, atmospheric and warm. The overlay is flat, cool, weightless and exact. Muted contrast, no dramatic colour grading. Composition weighted to the lower two thirds so the sky reads as empty space. 21:9 aspect ratio.
>
> Avoid entirely: glowing circuitry, holographic panels, floating hexagons, targeting brackets with corner ticks, chrome or robotic elements, blue-orange colour grading, volumetric god rays, lens flare, neon, and any large rendered text.

## Why it is built this way

**The subject carries the concept, not a metaphor.** No robot centurions, no glowing brains, no half-machine faces. The idea is legible from the geometry alone: a machine has looked at a battlefield and drawn a conclusion on it. The exposed left flank and the arc toward it are the directive, rendered.

**The overlay is one pixel and does not glow.** This is the instruction most likely to be ignored, and it is the one that matters. The moment the cyan layer glows, blooms or throws light on the dust, it stops reading as annotation and starts reading as science fiction, which is the cliché the whole image is trying to avoid. It should look like a draughtsman's line, not an interface.

**The palette is deliberately dulled.** Sun-bleached and oxidised rather than saturated. Cyan against warm neutral reads cleanly; cyan against a heavily graded orange battlefield turns into the blue-orange blockbuster look and loses its precision.

**The negative list is specific because generic negatives do not work.** "No sci-fi" gets ignored. "No floating hexagons, no corner-tick targeting brackets, no volumetric god rays" gets obeyed.

## Two levers if the first result misses

**If it reads as too much illustration and not enough photograph:** replace "painterly photographic realism" with "shot on 85mm, shallow depth of field on the near cohort, natural light only" and add "photographic".

**If the overlay dominates or looks like a video game HUD:** cut the numeric labels to two, drop the per-unit rectangles down to three, and add "the overlay covers less than a tenth of the frame and is easy to miss at first glance."

## Matching the mockup

If you want the hero to sit beside the overlay mockup as one visual system, pin the cyan to `#5fd0e0` by adding: "the overlay colour is a pale desaturated cyan, hex 5fd0e0, used at roughly 70 percent opacity."
