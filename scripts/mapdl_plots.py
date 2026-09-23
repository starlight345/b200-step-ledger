#!/usr/bin/env python3
"""Produce the MAPDL picture evidence: mesh, field, and a through-thickness section.

The V-1 and V-2 runs already reported numbers. A reader cannot tell from a number that a
finite-element model was actually built and solved, so this regenerates the same V-2 decks
with the graphics driver on and writes PNGs of the mesh and the temperature field.

Nothing about the physics changes -- the deck bodies come from mapdl_hotspot.deck()
unmodified and only a /POST1 graphics block is appended.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapdl_hotspot as H

GFX = """
/POST1
SET,LAST
/SHOW,PNG
/GFILE,1600
/RGB,INDEX,100,100,100,0
/RGB,INDEX,80,80,80,13
/RGB,INDEX,60,60,60,14
/RGB,INDEX,0,0,0,15
/PLOPTS,INFO,3
/PLOPTS,FRAME,0
/PLOPTS,LOGO,0
/PLOPTS,DATE,0
/TRIAD,OFF
ALLSEL,ALL
/VIEW,1,1,1,1
/ANG,1
/AUTO,1
/TYPE,1,0
! --- 1. the mesh itself, coloured by material, so the stack-up is visible
/PNUM,MAT,1
/NUMBER,1
/TITLE, 3D FE model: SOLID70, %s elements, quarter symmetry
EPLOT
! --- 2. the solved temperature field over the whole quarter-die
/PNUM,MAT,0
/NUMBER,0
/TITLE, Steady-state tier temperature rise [K]
PLNSOL,TEMP
! --- 3. through-thickness section near the active patch. z is 559 um against a
!     2000 um half-span, so the full model renders as a plate; slicing a narrow
!     x-band at y~0 gives a cross-section with a readable aspect ratio.
ESEL,S,CENT,Y,0,%.9e
ESEL,R,CENT,X,0,%.9e
/VIEW,1,0,-1,0
/ANG,1
/AUTO,1
! 3a. the section MESH, coloured by material -- this is the stack-up made visible
/PNUM,MAT,1
/NUMBER,1
/TITLE, Section mesh: TIM / Si / logic / BEOL / SRAM tier
EPLOT
! 3b. the same section, solved
/PNUM,MAT,0
/NUMBER,0
/TITLE, Section: steady-state rise [K], tier at top, sink at bottom
PLNSOL,TEMP
%s
ALLSEL,ALL
/SHOW,CLOSE
FINISH
"""

def plot_deck(patch_um, band_um=60.0, xspan_um=400.0):
    body = H.deck(patch_um=patch_um)
    # drop the original trailing POST1 block; we re-open POST1 with graphics
    cut = body.index('/POST1')
    head, tail = body[:cut], body[cut:]
    keep = tail[:tail.index('/OUT\n')+len('/OUT\n')] if '/OUT\n' in tail else tail
    nel = body.count('EGEN') and 'structured' or 'structured'
    # the 100 um patch peaks at 425 K, which saturates an auto scale and renders the
    # whole domain as one colour. Cap the contour so the SPREADING is what is visible.
    capped = ('/CONTOUR,1,9,0,1,9\n/TITLE, Same section, contour capped at 9 K to show spreading\n'
              'PLNSOL,TEMP\n/CONTOUR,1,AUTO') if patch_um else ''
    gfx = GFX % (nel, band_um*1e-6, xspan_um*1e-6, capped)
    return head + keep + gfx

if __name__ == '__main__':
    out = os.path.join(os.path.dirname(__file__), '..', 'assets', 'mapdl')
    os.makedirs(out, exist_ok=True)
    for tag, patch in [('plot_full', None), ('plot_100um', 100.0)]:
        p = os.path.join(out, tag + '.dat')
        open(p, 'w').write(plot_deck(patch))
        print(f'wrote {os.path.relpath(p)}  ({len(open(p).read().splitlines())} lines)')
