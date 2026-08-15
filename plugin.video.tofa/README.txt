tofa for Kodi
=============

A client for the tofa media server (api.tofa.tv).

It is first of all a PROGRAM. Under Programs, "tofa" opens a complete TV
interface: Home, Browse, Discover, Search, title detail, its own player
chrome and Settings. That is the add-on.

It also registers as a video source, so the same library appears under
Video add-ons for widgets, favourites and Kodi's own containers. That
half is a convenience, not a second version of the interface.

English only. The interface text lives in the screens and the code
rather than in a translatable string table, so there is nothing for a
translator to work against yet.


Who it is for
-------------

Three kinds of viewer, and it is built for all three at once.

People who want everything their files actually hold. A Dolby Vision
Profile 7 media file with its full enhancement layer, a 3D MVC title in
frame packing, a lossless TrueHD or DTS-HD track meant for the amplifier
rather than for the TV's speakers -- none of that survives being
re-encoded on the way past. So this add-on's job is to get out of the
way: it negotiates DirectPlay or DirectFile and hands Kodi the original
stream, then lets Kodi and your hardware do what they are capable of.
What your box can play, you get. What it cannot, no client can talk it
into.

People who want tofa's own experience inside Kodi, rather than a generic
listing of a tofa library. The screens, the artwork, the motion and the
wording follow tofa's design for its own TV apps, and where this client
knowingly differs, it is because Kodi cannot do the thing rather than
because nobody looked.

People watching on a 4K screen. Every layout is drawn at 4K and every
piece of artwork ships at twice the size it is displayed at, so text
edges and rounded corners stay crisp on a big panel instead of going
soft. It runs perfectly well at 1080p; it is simply not designed down to
it.


Server compatibility
--------------------

Built against tofa media server 0.9.30. Older servers are not refused, but
they are not supported either: this add-on carries no backward-compatibility
paths, so on an older server some screens will be missing or wrong rather
than degrading gracefully. It says so once per session when it sees one.

This line is checked at package time against the version the code actually
enforces (resources/lib/serverversion.py), so it cannot quietly go stale.


Staying up to date
------------------

If you installed this by hand from a zip, it will never update itself.
Kodi only offers an add-on update when the add-on came from a repository,
and a zip on your disk is not one. That is worth knowing rather than
discovering a year later on a version that predates half this file.

The update channel is a repository add-on you install once:

  1. Settings -> System -> Add-ons -> turn ON "Unknown sources". Kodi
     refuses to install from a zip without it, and says so only when you
     try.
  2. Settings -> File manager -> Add source
         https://tofa.cinemaone.ch
     Kodi cannot guess a name for an https source and will not accept an
     empty one. Call it "tofa".
  3. Settings -> Add-ons -> Install from zip file -> tofa ->
     repository.tofa-1.0.1.zip
  4. Settings -> Add-ons -> Install from repository ->
     tofa Add-on Repository -> Video add-ons -> "tofa for Kodi"
  5. Start it from Program add-ons -> "tofa for Kodi". That is the
     television interface. The Videos entry is the plain directory
     listing -- useful under any skin, and not the same thing.

Kodi then keeps this add-on current on its own. Installing the repository
over a hand-installed copy is fine and does not lose your pairing or your
settings.

Nothing about this is required. A hand-installed zip works exactly as
well; it simply stays where it is until you replace it yourself.


Audio when the server transcodes
--------------------------------

Picking any quality below Original makes the server transcode, and a
transcode has to re-encode the audio as well as the video. Left to its
default the server sends stereo AAC, which throws away a 5.1 or 7.1
soundtrack for no saving -- the surround rendition costs the same
bitrate.

So this add-on asks for E-AC-3 5.1 instead, but only when your audio
output can actually take it. It reads that from Kodi's own settings
(Settings -> System -> Audio) rather than assuming:

  - "Allow passthrough" on with Dolby Digital Plus enabled: the stream is
    passed to your AVR untouched.
  - A multichannel output without passthrough: Kodi decodes it and your
    output still carries 5.1.
  - A stereo output that cannot bitstream: nothing is asked for and you
    get stereo, which is the correct answer for that output.

Nothing here affects Original, which is not transcoded at all.


Artwork storage
----------------

Artwork is downloaded once and kept in the add-on's own data folder
(userdata/addon_data/plugin.video.tofa/artcache), and Kodi is pointed at
those files rather than at the server.

The reason is that the server's image links carry a credential that
rotates every hour, and Kodi treats a changed link as a different
picture -- so the same poster was being downloaded and re-cached over and
over. One device had accumulated 11,489 cached copies of 2,520 images.

Settings -> This Device controls it:

  Artwork storage limit   how much disk it may use (1 GB by default).
                          Over the limit, the oldest files go first and
                          are downloaded again when next needed.
  Clear artwork cache     empties it now, and removes the matching entries
                          from Kodi's own texture cache. Artwork downloads
                          again as you browse; nothing else is affected.

A background task keeps it inside the limit on its own, so neither
control is something you need to visit.


Unofficial
-----------

This is an unofficial tofa client, engineered with the tofa team, who
also help support it.

Unofficial means it is not a tofa product and carries no guarantee from
them. It is not built in isolation either: the tofa team helped engineer
it and has agreed to provide some support for it (2026-08-03). Settings
-> Privacy & About shows the same statement, and the Report a Problem
code on that page is the route to that support.

See LICENSE.txt for this add-on's own license (GPL-2.0-only). That licence
is a condition of the ported code credited below, not an independent
choice.


No warranty
-----------

This software is provided "as is", without warranty of any kind, express
or implied -- including, but not limited to, the implied warranties of
merchantability and fitness for a particular purpose. The entire risk as
to its quality and performance is with you, and no contributor is liable
for any damages arising out of its use, including loss of data or a
device left in a state you did not ask for.

That is the plain-English version of sections 11 and 12 of the GPL in
LICENSE.txt, which is the text that actually governs. It is restated
here because this add-on writes outside itself -- it copies fonts into
your active skin and can patch its seek bar, both with your consent, and
both described under "What this add-on changes outside itself" below.


Trademarks
----------

"tofa" is used with the tofa team's agreement, as are the fox marks; this
remains an unofficial client, and the name is theirs.

Dolby, Dolby Vision, Dolby Atmos and TrueHD are trademarks of Dolby
Laboratories. DTS, DTS-HD and DTS:X are trademarks of DTS, Inc. Kodi is
a trademark of the XBMC Foundation. Every other product or company name
here belongs to its owner.

They appear because a viewer needs to know which format a file is in and
what their equipment will do with it. No affiliation with, sponsorship
by, or endorsement from any of them is claimed or implied.


AI assistance
--------------

This project is written with AI assistance, and says so rather than
leaving you to guess. Every part of it is specified, reviewed and tested
on real devices by a developer with many years of professional software
experience; the assistant is a tool in that process, not a substitute
for it. Bugs here are ours.


Credits: plex-for-kodi
-----------------------

This add-on owes a large debt to plex-for-kodi
(https://github.com/plexinc/plex-for-kodi), GPL-2.0, and to pannal's
maintained fork of it, PM4K / PlexMod for Kodi
(https://github.com/pannal/plex-for-kodi). Kodi gives a Python add-on
almost nothing for building a real TV interface -- no window framework,
no managed lists, no focus plumbing -- and plex-for-kodi is the project
that worked out how to do it. Both code and ideas here come from reading
it.

Ported or adapted code (see each file's own header for exactly what was
kept and what was dropped):

  resources/lib/windows/kodigui.py       the window framework: BaseWindow,
                                         BaseDialog, ControlledWindow,
                                         ManagedListItem/ManagedControlList,
                                         PropertyTimer, WindowProperty and
                                         the rest
  resources/lib/windows/background.py    the background/transition window
  resources/lib/windows/windowutils.py   window helper mixins
  resources/skins/Main/skin.xml          the add-on skin's own descriptor

Designs and behaviours learned from its source rather than copied:

  - the player's own structure: a script entry point that opens a window
    UI directly, instead of going through a plugin:// directory listing
  - chapter skipping, including the ~2s grace that makes "previous
    chapter" restart the chapter you are in before it steps back one
  - which Kodi actions a player should answer at all (play/pause/stop,
    next/previous item, the chapter keys)
  - how to stop Kodi stretching a circular image mask into an oval
    (scalediffuse on <aspectratio>, not on <texture>)

The screen controllers, every screen layout under
resources/skins/Main/1080i/, the tofa logo and brand art, and everything
that talks to the tofa server are original to this add-on, built on top
of that framework.


Driving the stats overlay from JSON-RPC
----------------------------------------

The player's stats readout (8.11) has three states -- off, a small pill,
and the full panel -- reachable from the stats button in the player's own
control row and from the number keys 1, 2 and 3. It can also be set
remotely, which is what a home-automation button or a scripted test wants:

    {
      "jsonrpc": "2.0", "id": 1,
      "method": "JSONRPC.NotifyAll",
      "params": {
        "sender": "plugin.video.tofa",
        "message": "stats",
        "data": { "mode": "panel" }
      }
    }

`mode` is one of:

    off      hide the readout
    pill     the compact one-line readout
    panel    the full panel
    cycle    step to the next of the three

A bare string is accepted too (`"data": "panel"`), since it is the obvious
thing to try. Anything else is ignored and logged rather than guessed at.

Why a notification and not a method of its own: Kodi's JSON-RPC method
list is compiled into Kodi, so no add-on can add `tofa.SetStats` or
anything like it. `JSONRPC.NotifyAll` is the only channel that carries
arbitrary messages to a running add-on.

Three things about that channel are worth knowing before you write
against it, because none of them is obvious from Kodi's documentation:

  - Kodi prefixes the message, so `"message": "stats"` is delivered to
    add-ons as `Other.stats`. Only the `message` value goes in the call.
  - `sender` is a label, not a credential: any caller Kodi accepts can
    claim to be this add-on. Access is controlled at Kodi's web server
    instead, under Settings -> Services -> Control. "Require
    authentication" is ON by default (user `kodi`, no password until you
    set one), and "Enable SSL" encrypts the traffic if you put a
    certificate at special://userdata/server.pem and its key at
    server.key. Turning authentication off leaves the port open to
    anything that can reach it. That is acceptable for an overlay, and
    is the reason this channel carries nothing else.
  - It only reaches a player that is already open. There is no queue:
    a notification sent while nothing is playing is discarded, and the
    mode is deliberately not remembered for the next playback.

It applies on the player's next 200ms tick rather than the instant it
arrives, because Kodi delivers notifications on its own thread and this
add-on does not touch the interface from there.

From a shell, with Kodi's web server enabled:

    curl -s -X POST -H 'Content-Type: application/json' \
      http://KODI-HOST:8080/jsonrpc -d '{"jsonrpc":"2.0","id":1,
      "method":"JSONRPC.NotifyAll","params":{"sender":"plugin.video.tofa",
      "message":"stats","data":{"mode":"cycle"}}}'


What this add-on changes outside itself
----------------------------------------

Kodi gives an add-on no supported way to do three things this add-on
needs, so it makes three changes elsewhere on your system. All three are
listed in a single dialog and NOTHING is written until you confirm it;
declining is remembered, and Settings -> This Device is the way back in.
All three take effect only after Kodi restarts.

  1. Your ACTIVE SKIN's Font.xml, plus tofa's .ttf files copied into that
     skin's fonts folder. Kodi's font manager loads fonts from the active
     skin and nowhere else, so an add-on cannot ship its own. Every entry
     is prefixed "tofa_" and so cannot collide with the skin's own fonts.

  2. <imageres> in your advancedsettings.xml, raised to 1080. Kodi
     otherwise caches every texture at 720px tall, which visibly softens
     full-screen backdrops even on a 1080p display.

  3. One extra <visible> condition in your active skin's
     DialogSeekBar.xml:

         <visible>String.IsEmpty(Window(10000).Property(plugin.video.tofa.player_open))</visible>

     tofa's player draws its own transport and scrubber. Without this,
     your skin's seek bar slides in over the top of it whenever playback
     is paused or seeked. Kodi has no setting for this and no API to
     suppress it -- Dialog.Close(seekbar) is undone by the next seek, and
     the OSD outranks add-on dialogs, so the skin's XML is the only place
     it can be said. This is not a novel hack: plex-for-kodi's companion
     skin, Plextuary, carries the same condition on the same window for
     its own player. That property is set only while tofa's own player is
     open, so your seek bar is untouched for Kodi's own playback and for
     every other add-on.

     Removing the marked two lines restores it, as does switching skin.

If your skin lives on a read-only filesystem -- CoreELEC and LibreELEC
ship theirs on a squashfs -- changes 1 and 3 cannot be made in place, so
the whole skin is first copied into userdata (special://home/addons/) and
the copy is patched. Kodi then prefers the copy. Note that a later skin
UPDATE can overwrite either patch; the add-on notices and offers to
reapply.


Third-party assets
-------------------

Fonts
~~~~~~

Kodi gives a script add-on no way to name a font it has not registered, so
this add-on ships its own and injects them into whatever skin is active,
at runtime (resources/lib/fontinstall.py), rather than depending on the
host skin's font table. Every .ttf under resources/skins/Main/fonts/ is an
unmodified redistribution of the upstream release.

  Inter Tight 3.004 -- the interface typeface, used for essentially all
  text in the window UI.
      inter_tight_regular.ttf, inter_tight_semibold.ttf,
      inter_tight_bold.ttf
      Copyright 2022 The Inter Project Authors
      (https://github.com/rsms/inter-tight), by Rasmus Andersson.
      SIL Open Font License, Version 1.1.

  Roboto Mono 3.001 -- used where characters must line up or must not be
  misread: the sign-in device code and its URL, and the values in the
  player's stats overlay.
      RobotoMono-Regular.ttf, RobotoMono-Bold.ttf
      Copyright 2015 The Roboto Mono Project Authors
      (https://github.com/googlefonts/robotomono).
      SIL Open Font License, Version 1.1.

The OFL requires its notice to travel with the font itself, not merely to
be cited, so the full license text is bundled alongside them at
resources/skins/Main/fonts/OFL.txt. Neither family declares a Reserved
Font Name, and neither has been subsetted, renamed or otherwise altered.

Icons
~~~~~~

Icons throughout the window UI (top nav bar, Browse's sidebar and its
Sort/Filter/Quality controls, the player's transport, and others) are
from Lucide (https://lucide.dev), used under its ISC License, with a
subset of icons additionally under the MIT License -- see
resources/skins/Main/media/LUCIDE_LICENSE.txt for the full text.

They are drawn as text glyphs from Lucide's own prebuilt icon font
(resources/skins/Main/fonts/lucide-icons.ttf, redistributed unmodified)
rather than as pre-rasterized images, and are registered through the same
fontinstall.py path as the text fonts above, so they stay crisp at any
size instead of being fixed-resolution rasters. That font carries no
license metadata of its own in its `name` table; LUCIDE_LICENSE.txt is
what governs it.
