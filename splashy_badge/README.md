Splashy Badge is a screen-filling glass water tank with floating 3D lettering and Mona for the GitHub Universe 2026 badge.

Tilt the badge to slosh the water and gently shift the tank's perspective.
Hold it comfortably when opening the app; that pose becomes its neutral position.

The first time it opens, setup appears so you can make it yours. Your handle
starts as the badge's `GITHUB_USERNAME` (the one the Badge app shows), the
title as `universe`, and pronouns blank.

| Control | Action |
| --- | --- |
| Right-side physical Up / Down | Raise / lower the water; hold to keep adjusting |
| Bottom physical Left / Right / Select | Drop your extruded handle / title / pronouns into the pool. Each word appears once; once it is in the pool, that button drops a 3D Mona instead (A lets the words drop again) |
| Touch D-pad | Blow wind in the chosen direction |
| Touch A (Select) | Clear all floating objects |
| Touch B (Back) | Cycle the tank edge color, starting with green |
| Touch Menu | Open setup to choose your handle, title, and pronouns |
| Home | Return to the badge menu |

Setup: Up / Down choose a line, Left / Right cycle presets, and A opens an
on-screen keyboard to type your own words (B deletes, Menu finishes typing).
Choose "Save & return", or press B or Menu, to save and go back to the pool,
which also recenters motion. Labels are up to 16 characters; long ones shrink
to fit, and an empty label makes that button drop only Monas. Your choices are
saved with `badgeware.State` (in `/state/splashy_badge.json`) and kept across restarts.

The screen is the front face of the tank. Its corners connect to an inset,
parallel back face, seen from slightly above the waterline; motion subtly
shifts the perspective without moving the front corners. Translucent water
reveals submerged edges and moving floor light patterns. The surface is
glossy: back rows reflect more light (a Fresnel effect), crests catch
specular highlights, glints sparkle, and the waterline shines against the glass.

Up to nine objects can float at once. Words use the badge's own Lato Black
vector font outlines, with open counters, extruded layered sides, shading,
and independent 3D rotation. Mona is the home screen's 3D model, rendered
with glossy lighting by the badge's pico3d engine. The handle is drawn noticeably
larger, since this is still a name tag. A message appears when full.
Objects are heavy: they plunge below the surface with a big splash, bob back
up, wobble and tip with passing waves, drift, collide, and ripple the water
as they settle partly below the tinted surface.
Every object gets a random weight: light ones ride high, medium ones float low,
and heavy ones sink and come to rest on the floor, visible through the water.
Landings throw a crater, crown rings, and arcing spray; falling droplets
leave their own ripples.
The water percentage appears briefly when adjusting the level; otherwise
there are no persistent headings or control labels obscuring the tank.
The app uses the onboard accelerometer and gyroscope, with no external hardware,
network, dependencies, or firmware changes; its only write is your saved labels.

This is a small real-time height-field simulation, not desktop SPH fluid dynamics
or full volumetric fluid reconstruction. It runs entirely in MicroPython.
Wave shading runs in a viper-compiled integer kernel and physics sub-steps are
capped, so it stays smooth with a full tank (about 14 frames per second
with nine objects settled, 15 with four). Each Mona is rendered into a cached
sprite and re-rendered only when her pose changes noticeably, at most two per
frame, so extra Monas cost under 1 ms each.
