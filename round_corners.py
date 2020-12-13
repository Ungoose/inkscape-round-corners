#!/usr/bin/env python
# coding=utf-8
#
# Copyright (C) 2020 Juergen Weigert, jnweiger@gmail.com
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
# v0.1, 2020-11-08, jw	- initial draught, finding and printing selected nodes to the terminal...
# v0.2, 2020-11-08, jw	- duplicate the selected nodes in their superpaths, write them back.
# v0.3, 2020-11-21, jw	- find "meta-handles"
# v0.4, 2020-11-26, jw	- alpha and trim math added. trimming with a striaght line implemented, needs fixes.
#                         Option 'cut' added.
# v0.5, 2020-11-28, jw	- Cut operation looks correct. Dummy midpoint for large arcs added, looks wrong, of course.
# v1.0, 2020-11-30, jw	- Code completed. Bot cut and arc work fine.
# v1.1, 2020-12-07, jw	- Replaced boolean 'cut' with a method selector 'arc'/'line'. Added round_corners_092.inx
#                         and started backport in round_corners.py -- attempting to run the same code everywhere.
# v1.2, 2020-12-08, jw  - Backporting continued: option parser hack added. Started effect_wrapper() to prepare self.svg
#                         UNFINISHED: self.svg only has an empty getElementById() method.
#
# Nasty side-effect: as the node count increases, the list of selected nodes is incorrect
# afterwards. We have no way to give inkscape an update.
#
"""
Rounded Corners

This extension operates on selected sharp corner nodes and converts them to a fillet (bevel,chamfer).
An arc shaped path segment with the given radius is inserted smoothly.
The fitted arc is approximated by a bezier spline, as we are doing path operations here.
When the sides at the corner are straight lines, the operation never move the sides, it just shortens them to fit the arc.
When the sides are curved, the arc is placed on the tanget line, and the curve may thus change in shape.

Selected smooth nodes are skipped.
Cases with insufficient space (180deg turn or too short segments/handles) are warned about.

References:
 - https://gitlab.com/inkscape/extensions/-/wikis/home
 - https://gitlab.com/inkscape/extras/extensions-tutorials/-/blob/master/My-First-Effect-Extension.md
 - https://gitlab.com/inkscape/extensions/-/wikis/uploads/25063b4ae6c3396fcda428105c5cff89/template_effect.zip
 - https://inkscape-extensions-guide.readthedocs.io/en/latest/_modules/inkex/elements.html#ShapeElement.get_path
 - https://inkscape.gitlab.io/extensions/documentation/_modules/inkex/paths.html#CubicSuperPath.to_path

 - https://stackoverflow.com/questions/734076/how-to-best-approximate-a-geometrical-arc-with-a-bezier-curve
 - https://hansmuller-flex.blogspot.com/2011/10/more-about-approximating-circular-arcs.html
 - https://itc.ktu.lt/index.php/ITC/article/download/11812/6479         (Riskus' PDF)

The algorithm of arc_bezier_handles() is based on the approach described in:
A. Riškus, "Approximation of a Cubic Bezier Curve by Circular Arcs and Vice Versa,"
Information Technology and Control, 35(4), 2006 pp. 371-378.
"""

# python2 compatibility:
from __future__ import print_function

import inkex
import sys, math, pprint

if not hasattr(inkex, 'EffectExtension'):       # START OF INKSCAPE 0.92.X COMPATIBILITY HACK
  """ OOPS, the code **after** this if conditional is meant for inkscape 1.0.1,
      but we seem to be running under inkscape 0.92.x today.
      Well, to make the new code work in the old environment, in here, we do the
      exact oposite of 1.0.1's /usr/share/inkscape/extensions/inkex/deprecated.py
      (which would make old code run in the new 1.0.1 environment.)

      old and new:
      - self.options= {'selected_nodes': ['path1684:0:2', 'path1684:0:0'], 'radius': 2.0, 'ids': ['path1684'], 'method': 'arc'}

      old style:
      - self.document= <lxml.etree._ElementTree object at 0x7f5c2b1a77e8>
      - self.document.getroot() =  <Element {http://www.w3.org/2000/svg}svg at 0x7f5c2b1a78c0>

      new style:
      - self.svg= <class 'inkex.elements._svg.SvgDocumentElement'>
      - self.svg.getElementById('path1684') =  <class 'inkex.elements._polygons.PathElement'>
        ## maybe not even based on an lxml ElephantTree any more? Let's check the new code...
  """
  def compat_add_argument(pars, *args, **kw):
    """
       Provide an add_argument() method so that add_argument() can use the new api,
       but implemented in terms of the old api.
    """
    # convert type method into type string as needed, see deprecated.py def add_option()
    if 'type' in kw:
      kw['type'] = { str: 'string', float: 'float', int: 'int', bool: 'inkbool' }.get(kw['type'])
    if 'action' not in kw:
      kw['action'] = 'store'
    pars.add_option(*args, **kw)


  def effect_wrapper(self):
    """
       A cheap plastic immitation if inkscape-1.0.1's SvgDocumentElement() class found in
       /usr/share/inkscape/extensions/inkex/elements/_svg.py
       We add an svg object to the old api, so that new style code can run.
       Note: only a very minimal set of methods is supported, and those that are, in a very primitive way.
    """

    class MySvgPath():
      def __init__(self, el):
        self.element = el                       # original lxml.etree._Element
        self.d = el.get('d')                    # must exist, else it is not a path :-)
        print('MySvgPath sodipodi:nodetypes=', el.get('{'+el.nsmap['sodipodi']+'}nodetypes'), file=sys.stderr)
        print('MySvgPath style=', el.get('style'), file=sys.stderr)
        print('MySvgPath d=', self.d, file=sys.stderr)

      def to_superpath(self):
        print('MySvgElement to_superpath ', self.d, file=sys.stderr)
        raise(Exception("to_superpath() not impl."))


    class MySvgElement():
      def __init__(self, el):
        self.element = el                       # original lxml.etree._Element; element.getroottree() has the svg document
        self.tag = el.tag.split('}')[-1]        # strip any namespace prefix. '{http://www.w3.org/2000/svg}path'
        print("MySvgElement tag=", self.tag, " attrib=", el.attrib, " from ", el.base, ":", el.sourceline, file=sys.stderr)
        if self.tag == 'path':
          self.path = MySvgPath(el)
        else:
          print("MySvgElement not implemented for tag=", tag, file=sys.stderr)

      def apply_transform(self):
        t = self.element.get('transform')
        print('MySvgElement transform=', t, file=sys.stderr)
        if t is not None:
          raise(Exception("apply_transform() not impl."))


    class MySvgDocumentElement():
      def __init__(self, document):
        self.tree = document
        self.root = document.getroot()
        self.NSS = self.root.nsmap.copy()       # Or should we just use inkex.NSS instead? That has key 'inx', but not 'inkscape' ...
        self.NSS.pop(None)                      # My documents nsmap has cc,svg,inkscape,rdf,sodipodi, and None: http://www.w3.org/2000/svg
        if 'inx' not in self.NSS and 'inkscape' in self.NSS:
          self.NSS['inx'] = self.NSS['inkscape']

      def getElementById(self, id):
        print("MySvgDocumentElement.getElementById: svg=", self.tree, " svg.root=", self.root, " ID=", id, file=sys.stderr)
        el_list = self.root.xpath('//*[@id="%s"]' % id, namespaces=self.NSS)
        print("el_list=", el_list, file=sys.stderr)
        if len(el_list) < 1:
          return None
        return MySvgElement(el_list[0])         # Do we need more? document root is accessible via el_list[0].getroottree()


    self.svg = MySvgDocumentElement(self.document)
    self.wrapped_effect()


  def init_wrapper(self):
    from types import MethodType

    ## to backport the option parsing, we wrap the __init__ method and introduce a compatibility shim.
    # we must call add_arguments(), that seems to be done by EffectExtension.__init__() which we don't have.
    # have Effect.__init__() instead, which expects to be subclassed. We cannot subclass, as we don't want to
    # touch the class code at all. Instead exchange the Effect.__init__() with this wrapper, to hook in
    # new style semantics into the old style inkex.Effect superclass.
    # We also we must convert from new style pars.add_argument() calls to old style
    # self.OptionParser.add_option() -- this is done by the compat_add_argument wrapper.
    #
    self.wrapped_init()                                    # call early, as it adds the OptionParser to self ...

    # We add an add_argument method to the OptionParser. A direct assignment would discard the indirect object.
    self.OptionParser.add_argument = MethodType(compat_add_argument, self.OptionParser)

    # so that we can now call the new style add_arguments() method
    self.add_arguments(self.OptionParser)

    # self.document is not loaded yet, so we must prepare self.svg later.
    self.run = self.affect      # MethodType(my_run, self) does not help. self.document is still none inside my_run()

    # try wrap our own effect() method, that must be late enough...
    self.wrapped_effect = self.effect
    self.effect = MethodType(effect_wrapper, self)


  inkex.EffectExtension = inkex.Effect
  inkex.EffectExtension.wrapped_init = inkex.EffectExtension.__init__
  inkex.EffectExtension.__init__ = init_wrapper

# END OF INKSCAPE 0.92.X COMPATIBILITY HACK


__version__ = '1.2'     # Keep in sync with round_corners.inx line 16

debug = False           # True: babble on controlling tty
max_trim_factor = 0.5   # 0.5: can cut half of a segment length or handle length away for rounding a corner

class RoundedCorners(inkex.EffectExtension):

    def add_arguments(self, pars):              # an __init__ in disguise ...
      try:
        self.tty = open("/dev/tty", 'w')
      except:
        try:
          self.tty = open("CON:", 'w')        # windows. Does this work???
        except:
          self.tty = open(os.devnull, 'w')  # '/dev/null' for POSIX, 'nul' for Windows.
      if debug: print("RoundedCorners ...", file=self.tty)
      self.nodes_inserted = {}
      self.eps = 0.00001                # avoid division by zero
      self.radius = None
      self.max_trim_factor = max_trim_factor

      self.skipped_degenerated = 0      # not a useful corner (e.g. 180deg corner)
      self.skipped_small_count = 0      # not enough room for arc
      self.skipped_small_len = 1e99     # record the shortest handle (or segment) when skipping.

      pars.add_argument("--radius", type=float, default=2.0, help="Radius [mm] to round selected vertices")
      pars.add_argument("--method", type=str, default="arc", help="operation: one of 'arc' (default), 'arc+cross', 'line'")


    def effect(self):
        if debug:
          # SvgInputMixin __init__: "id:subpath:position of selected nodes, if any"
          print(self.options.selected_nodes, file=self.tty)

        self.radius = math.fabs(self.options.radius)
        self.cut = False
        if self.options.method in ('line'):
          self.cut = True
        if len(self.options.selected_nodes) < 1:
          raise inkex.AbortExtension("Need at least one selected node in the path. Go to edit path, click a corner, then try again.")
        if len(self.options.selected_nodes) == 1:
          # when we only trim one node, we can eat up almost everything,
          # no need to leave room for rounding neighbour nodes.
          self.max_trim_factor = 0.95

        for node in sorted(self.options.selected_nodes):
          ## we walk through the list sorted, so that node indices are processed within a subpath in ascending numeric order.
          ## that makes adjusting index offsets after node inserts easier.
          ss = self.round_corner(node)


    def round_corner(self, node_id):
      """ round the corner at (adjusted) node_idx of subpath
          Side_effect: store (or increment) in self.inserted["pathname:subpath"] how many points were inserted in that subpath.
          the adjusted node_idx is computed by adding that number (if exists) to the value of the node_id before doing any manipulation
      """
      s = node_id.split(":")
      path_id = s[0]
      subpath_idx = int(s[1])
      subpath_id = s[0] + ':' + s[1]
      idx_adjust = self.nodes_inserted.get(subpath_id, 0)
      node_idx = int(s[2]) + idx_adjust

      elem = self.svg.getElementById(path_id)
      elem.apply_transform()       # modifies path inplace? -- We save later back to the same element. Maybe we should not?
      path = elem.path
      s = path.to_superpath()
      sp = s[subpath_idx]

      ## call the actual path manipulator, record how many nodes were inserted.
      orig_len = len(sp)
      sp = self.subpath_round_corner(sp, node_idx)
      idx_adjust += len(sp) - orig_len

      # convert the superpath back to a normal path
      s[subpath_idx] = sp
      elem.set_path(s.to_path(curves_only=False))
      self.nodes_inserted[subpath_id] = idx_adjust

      # Debugging is no longer available or not yet implemented? This explodes, although it is
      # documented in https://inkscape.gitlab.io/extensions/documentation/inkex.command.html
      # inkex.command.write_svg(self.svg, "/tmp/seen.svg")
      # - AttributeError: module 'inkex' has no attribute 'command'
      # But hey, we can always resort to good old ET.dump(self.document) ...


    def super_node(self, sp, node_idx):
      """ In case of node_idx 0, we need to use either the last, or the second-last node as a previous node.
          For a closed subpath, the last an the first node are identical, then we use the second-last.
          In case of the node_idx being the last node, we already know that the subpath is not closed,
          we use 0 as the next node.

          The direction sn.prev.dir does not really point to the coordinate of the previous node, but to the end of the
          next-handle of the prvious node. This is the same when there are straight lines. The absence of handles is
          denoted by having the same coordinates for handle and node.
          Same for next.dir, it points to the next.prev handle.

          The exact implementation here is:
          - sn.next.handle is set to a relative vector that is the tangent of the curve towards the next point.
            we implement four cases:
            - if neither node nor next have handles, the connection is a straight line, and next.handle points
              in the direction of the next node itself.
            - if the curve between node and next is defined by two handles, then sn.next.handle is in the direction of the
              nodes own handle,
            - if the curve between node and next is defined one handle at the node itself, then sn.next.handle is in the
              direction of the nodes own handle,
            - if the curve between node and next is defined one handle at the next node, then sn.next.handle is in the
              direction from the node to the end of that other handle.
          - when trimming back later, we move along that tangent, instead of following the curve.
            That is an approximation when the segment is curved, and exact when it is straight.
            (Finding exact candidate points on curved lines that have tangents with the desired circle
            is beyond me today. Multiple candidates may exist. Any volunteers?)
      """
      prev_idx = node_idx - 1
      if node_idx == 0:
        prev_idx = len(sp) - 1
        # deep compare. all elements in sub arrays are compared for numerical equality
        if sp[node_idx] == sp[prev_idx]:
          prev_idx = prev_idx - 1
        else:
          self.skipped_degenerated += 1         # path ends here.
          return None

      # if debug: pprint.pprint({'node_idx': node_idx, 'len(sp)':len(sp), 'sp': sp}, stream=self.tty)
      if node_idx == len(sp)-1:
        self.skipped_degenerated += 1           # path ends here. On a closed loop, we can never select the last point.
        return None

      next_idx = node_idx + 1
      if next_idx >= len(sp): next_idx = 0
      t = sp[node_idx]
      p = sp[prev_idx]
      n = sp[next_idx]
      dir1 = [ p[2][0] - t[1][0], p[2][1] - t[1][1] ]           # direction to the previous node (rel coords)
      dir2 = [ n[0][0] - t[1][0], n[0][1] - t[1][1] ]           # direction to the next node (rel coords)
      dist1 = math.sqrt(dir1[0]*dir1[0] + dir1[1]*dir1[1])      # distance to the previous node
      dist2 = math.sqrt(dir2[0]*dir2[0] + dir2[1]*dir2[1])      # distance to the next node
      handle1 = [ t[0][0] - t[1][0], t[0][1] - t[1][1] ]        # handle towards previous node (rel coords)
      handle2 = [ t[2][0] - t[1][0], t[2][1] - t[1][1] ]        # handle towards next node (rel coords)
      if handle1 == [ 0, 0 ]: handle1 = dir1
      if handle2 == [ 0, 0 ]: handle2 = dir2

      prev = { 'idx': prev_idx, 'dir':dir1, 'handle':handle1 }
      next = { 'idx': next_idx, 'dir':dir2, 'handle':handle2 }
      sn = { 'idx': node_idx, 'prev': prev, 'next': next, 'x': t[1][0], 'y': t[1][1] }

      if dist1 < self.radius:
        if debug:
          print("subpath node_idx=%d, dist to prev(%d) is smaller than radius: %g < %g" %
                (node_idx, prev_idx, dist1, self.radius), file=sys.stderr)
          pprint.pprint(sn, stream=sys.stderr)
        if self.skipped_small_len > dist1: self.skipped_small_len = dist1
        skipped_small_count += 1
        return None

      if dist2 < self.radius:
        if debug:
          print("subpath node_idx=%d, dist to next(%d) is smaller than radius: %g < %g" %
                (node_idx, next_idx, dist2, self.radius), file=sys.stderr)
          pprint.pprint(sn, stream=sys.stderr)
        if self.skipped_small_len > dist2: self.skipped_small_len = dist2
        skipped_small_count += 1
        return None

      len_h1 = math.sqrt(handle1[0]*handle1[0] + handle1[1]*handle1[1])
      len_h2 = math.sqrt(handle2[0]*handle2[0] + handle2[1]*handle2[1])
      prev['hlen'] = len_h1
      next['hlen'] = len_h2

      if len_h1 < self.radius:
        if debug:
          print("subpath node_idx=%d, handle to prev(%d) is shorter than radius: %g < %g" %
                (node_idx, prev_idx, len_h1, self.radius), file=sys.stderr)
          pprint.pprint(sn, stream=sys.stderr)
        if self.skipped_small_len > len_h1: self.skipped_small_len = len_h1
        skipped_small_count += 1
        return None
      if len_h2 < self.radius:
        if debug:
          print("subpath node_idx=%d, handle to next(%d) is shorter than radius: %g < %g" %
                (node_idx, next_idx, len_h2, self.radius), file=sys.stderr)
          pprint.pprint(sn, stream=sys.stderr)
        if self.skipped_small_len > len_h2: self.skipped_small_len = len_h2
        skipped_small_count += 1
        return None

      if len_h1 > dist1: # shorten that handle to dist1, avoid overshooting the point
        handle1[0] = handle1[0] * dist1 / len_h1
        handle1[1] = handle1[1] * dist1 / len_h1
        prev['hlen'] = dist1
      if len_h2 > dist2: # shorten that handle to dist2, avoid overshooting the point
        handle2[0] = handle2[0] * dist2 / len_h2
        handle2[1] = handle2[1] * dist2 / len_h2
        next['hlen'] = dist2

      return sn


    def arc_c_m_from_super_node(self, s):
      """
      Given the supernode s and the radius self.radius, we compute and return two points:
      c, the center of the arc and m, the midpoint of the arc.

      Method used:
      - construct the ray c_m_vec that runs though the original point p=[x,y] through c and m.
      - next.trim_pt, [x,y] and c form a rectangular triangle. Thus we can
        compute cdist as the length of the hypothenuses under trim and radius.
      - c is then cdist away from [x,y] along the vector c_m_vec.
      - m is closer to [x,y] than c by exactly radius.
      """

      a = [ s['prev']['trim_pt'][0] - s['x'], s['prev']['trim_pt'][1] - s['y'] ]
      b = [ s['next']['trim_pt'][0] - s['x'], s['next']['trim_pt'][1] - s['y'] ]

      c_m_vec = [ a[0] + b[0],
                  a[1] + b[1] ]
      l = math.sqrt( c_m_vec[0]*c_m_vec[0] + c_m_vec[1]*c_m_vec[1] )

      cdist = math.sqrt( self.radius*self.radius + s['trim']*s['trim'] )    # distance [x,y] to circle center c.

      c = [ s['x'] + cdist * c_m_vec[0] / l,                      # circle center
            s['y'] + cdist * c_m_vec[1] / l ]

      m = [ s['x'] + (cdist-self.radius) * c_m_vec[0] / l,        # spline midpoint
            s['y'] + (cdist-self.radius) * c_m_vec[1] / l ]

      return (c, m)


    def arc_bezier_handles(self, p1, p4, c):
      """
      Compute the control points p2 and p3 between points p1 and p4, so that the cubic bezier spline
      defined by p1,p2,p3,p2 approximates an arc around center c

      Algorithm based on Aleksas Riškus and Hans Muller. Sorry Pomax, saw your works too, but did not use any.
      """
      x1,y1 = p1
      x4,y4 = p4
      xc,yc = c

      ax = x1 - xc
      ay = y1 - yc
      bx = x4 - xc
      by = y4 - yc
      q1 = ax * ax + ay * ay
      q2 = q1 + ax * bx + ay * by
      k2 = 4./3. * (math.sqrt(2 * q1 * q2) - q2) / (ax * by - ay * bx)

      x2 = xc + ax - k2 * ay
      y2 = yc + ay + k2 * ax
      x3 = xc + bx + k2 * by
      y3 = yc + by - k2 * bx

      return ([x2, y2], [x3, y3])


    def subpath_round_corner(self, sp, node_idx):
      sn = self.super_node(sp, node_idx)
      if sn is None: return sp          # do nothing. stderr messages are already printed.

      # from https://de.wikipedia.org/wiki/Schnittwinkel_(Geometrie)
      # wikipedia has an abs() in the formula, which extracts the smaller of the two angles.
      # we don't want that. We need to distinguish betwenn spitzwingklig and stumpfwinklig.
      #
      # The angle to be rounded is now between the vectors a and b
      #
      a = sn['prev']['handle']
      b = sn['next']['handle']
      a_len = sn['prev']['hlen']
      b_len = sn['next']['hlen']
      try:
        alpha = math.acos( (a[0]*b[0]+a[1]*b[1]) / ( math.sqrt(a[0]*a[0]+a[1]*a[1]) * math.sqrt(b[0]*b[0]+b[1]*b[1]) ) )
      except:
        # Division by 0 error means path folds back on itself here. No space to apply a radius between the segments.
        self.skipped_degenerated += 1
        return sp

      sn['alpha'] = math.degrees(alpha)

      # find the amount to trim back both sides so that a circle of radius self.radius would perfectly fit.
      if alpha < self.eps:
        # path folds back on itself here. No space to apply a radius between the segments.
        self.skipped_degenerated += 1
        return sp
      if abs(alpha - math.pi) < self.eps:
        # stretched. radius won't be visible, that is just fine. No need to warn about that.
        return sp
      trim = self.radius / math.tan(0.5 * alpha)
      sn['trim'] = trim
      if trim < 0.0:
        print("Error: at node_idx=%d: angle=%g°, trim is negative: %g" % (node_idx, math.degrees(alpha), trim), file=sys.stderr)
        return sp
      if trim > self.max_trim_factor*min(a_len, b_len):
        if debug:
          print("Skipping where trim > %g * hlen" % self.max_trim_factor, file=self.tty)
          pprint.pprint(sn, stream=self.tty)
        if self.skipped_small_len > self.max_trim_factor*min(a_len, b_len):
          self.skipped_small_len = self.max_trim_factor*min(a_len, b_len)
        self.skipped_small_count += 1
        return sp
      trim_pt_p = [ sn['x'] + a[0] * trim / a_len, sn['y'] + a[1] * trim / a_len ]
      trim_pt_n = [ sn['x'] + b[0] * trim / b_len, sn['y'] + b[1] * trim / b_len ]
      sn['prev']['trim_pt'] = trim_pt_p
      sn['next']['trim_pt'] = trim_pt_n

      if debug:
        pprint.pprint(sn, stream=self.tty)
        pprint.pprint(self.cut, stream=self.tty)
      # We replace the node_idx node by two nodes node_a, node_b.
      # We need an extra middle node node_m if alpha < 90° -- alpha is the angle between the tangents,
      # as the arc spans the remainder to complete 180° an arc with more than 90° needs the midpoint.

      # We preserve the endpoints of the two outside handles if they are non-0-length.
      # We know that such handles are long enough (because of the above max_trim_factor checks)
      # to not flip around when applying the trim.
      # But we move the endpoints of 0-length outside handles with the point when trimming,
      # so that they don't end up on the inside.
      prev_handle = sp[node_idx][0][:]
      next_handle = sp[node_idx][2][:]
      if prev_handle == sp[node_idx][1]: prev_handle = trim_pt_p[:]
      if next_handle == sp[node_idx][1]: next_handle = trim_pt_n[:]

      p1 = trim_pt_p[:]
      p7 = trim_pt_n[:]
      arc_c, p4 = self.arc_c_m_from_super_node(sn)
      node_a = [ prev_handle, p1[:], p1[:] ]    # deep copy, as we may want to modify the second handle later
      node_b = [ p7[:], p7[:], next_handle ]    # deep copy, as we may want to modify the first handle later

      if alpha >= 0.5*math.pi or self.cut:
        if self.cut == False:
          # p3,p4,p5 do not exist, we need no midpoint
          p2, p6 = self.arc_bezier_handles(p1, p7, arc_c)
          node_a[2] = p2
          node_b[0] = p6
        sp = sp[:node_idx] + [node_a] + [node_b] + sp[node_idx+1:]
      else:
        p2, p3 = self.arc_bezier_handles(p1, p4, arc_c)
        p5, p6 = self.arc_bezier_handles(p4, p7, arc_c)
        node_m = [ p3, p4, p5 ]
        node_a[2] = p2
        node_b[0] = p6
        sp = sp[:node_idx] + [node_a] + [node_m] + [node_b] + sp[node_idx+1:]

      # A closed path is formed by making the last node indentical to the first node.
      # So, if we trim at the first node, then duplicte that trim on the last node, to keep the loop closed.
      if node_idx == 0:
        sp[-1][0] = sp[0][0][:]
        sp[-1][1] = sp[0][1][:]
        sp[-1][2] = sp[0][2][:]

      return sp


    def clean_up(self):         # __fini__
      if self.tty is not None:
        self.tty.close()
      super(RoundedCorners, self).clean_up()
      if self.skipped_degenerated:
        print("Warning: Skipped %d degenerated nodes (180° turn or end of path?).\n" % self.skipped_degenerated, file=sys.stderr)
      if self.skipped_small_count:
        print("Warning: Skipped %d nodes with not enough space (Value %g is too small. Try a smaller radius?).\n" % (self.skipped_small_count, self.skipped_small_len), file=sys.stderr)


if __name__ == '__main__':
    RoundedCorners().run()
