Screenshots
===========

The six images addon.xml declares as <screenshot>, plus fanart.jpg, which is
a copy of 01-home.jpg. Kodi shows the screenshots as a filmstrip across the
top of the add-on information dialog -- the screen a user reads before
deciding to install -- and draws the fanart, heavily dimmed, behind the
add-on browser.

  01-home.jpg      Home: the hero and Continue Watching
  02-browse.jpg    Browse: the library grid and its sidebar
  03-detail.jpg    a title's detail hero
  04-cast.jpg      the same title's Cast & Crew page
  05-player.jpg    the player chrome over playback
  06-settings.jpg  Settings > Account

WHAT IS IN THEM. Only material that can be published. They were taken
against tofa's public-domain demo library -- Charade (1963), Nosferatu
(1922) and that shelf -- plus the Blender Foundation's open movies (Big Buck
Bunny, Tears of Steel), which are CC-BY.

Two screens are deliberately ABSENT. Discover and Search draw current
commercial studio posters from the metadata provider; nothing else here
does, and a screenshot is republished far more widely than a screen a user
scrolls past once.

06-settings.jpg is REDACTED: the account email in all three places it
appears, and the QR, which encodes an account-management URL. Blurred rather
than boxed so the layout still reads.

RETAKING THEM. 1920x1080, JPEG q90 -- 14MB of PNG became 1.8MB, which is
what six full-resolution screens cost the zip. Shoot with Kodi's own
screenshot action (a desktop capture will not match), and check
`debug.showloginfo` is off and `input.enablemouse` is false first: both have
spoiled reference shots before.

03-detail.jpg was retaken on 2026-08-14, same title and same framing. The
first one showed the action row as it was before the pills went to a uniform
325 with their contents anchored -- four different widths, each pill's icon
and text centred as a group -- so it advertised a layout the add-on no longer
has. Measured on the two files, the old row ran 360/270/269/243 and the new
one 360/325/325/325. A screenshot of a redesigned screen is stale the moment
the screen changes; check this row against a live shot after any Detail work.

fanart.jpg was the startup splash's final frame until 2026-08-14. It was
replaced because the icon is already the fox, so the splash frame said
nothing the icon had not: a backdrop of the app in use tells a reader more
than the logo twice. tools/gen_fanart.py, which assembled that frame from
the shipped splash strips, was retired with it.
