import cadquery

# FIXME: remove freecad dependency from this module...
#        right now I'm just trying to get it working.
import FreeCAD


def intersect(wp1, wp2, combine=True, clean=True):
    """
    Return geometric intersection between 2 cadquery.Workplane instances by
    exploiting.
    A n B = (A u B) - ((A - B) u (B - A))
    """
    solidRef = wp1.findSolid(searchStack=True, searchParents=True)

    if solidRef is None:
        raise ValueError("Cannot find solid to intersect with")
    solidToIntersect = None

    if isinstance(wp2, cadquery.CQ):
        solidToIntersect = wp2.val()
    elif isinstance(wp2, cadquery.Solid):
        solidToIntersect = wp2
    else:
        raise ValueError("Cannot intersect type '{}'".format(type(wp2)))

    newS = solidRef.intersect(solidToIntersect)

    if clean:
        newS = newS.clean()

    if combine:
        solidRef.wrapped = newS.wrapped

    return wp1.newObject([newS])

    #cp = lambda wp: wp.translate((0, 0, 0))
    #neg1 = cp(wp1).cut(wp2)
    #neg2 = cp(wp2).cut(wp1)
    #neg = neg1.union(neg2)
    #return cp(wp1).union(wp2).cut(neg)


def copy(wp):
    return wp.translate((0, 0, 0))


class CoordSystem(cadquery.Plane):
    """
    Defines the location, and rotation of an orthogonal 3 dimensional coordinate
    system.
    """

    @classmethod
    def from_plane(cls, plane):
        """
        :param plane: cadquery plane instance to base coordinate system on
        :type plane: :class:`cadquery.Plane`
        :return: duplicate of the given plane, in this class
        :rtype: :class:`CoordSystem`

        usage example:

        .. doctest::

            >>> import cadquery
            >>> from cqparts.utils.geometry import CoordSystem
            >>> obj = cadquery.Workplane('XY').circle(1).extrude(5)
            >>> plane = obj.faces(">Z").workplane().plane
            >>> isinstance(plane, cadquery.Plane)
            True
            >>> coord_sys = CoordSystem.from_plane(plane)
            >>> isinstance(coord_sys, CoordSystem)
            True
            >>> coord_sys.origin.z
            5.0
        """
        return cls(
            origin=plane.origin.toTuple(),
            xDir=plane.xDir.toTuple(),
            normal=plane.zDir.toTuple(),
        )

    @classmethod
    def from_transform(cls, matrix):
        r"""
        :param matrix: 4x4 3d affine transform matrix
        :type matrix: :class:`FreeCAD.Matrix`
        :return: a unit, zero offset coordinate system transformed by the given matrix
        :rtype: :class:`CoordSystem`

        Individual rotation & translation matricies are:

        .. math::

            R_z & = \begin{bmatrix}
                cos(\alpha) & -sin(\alpha) & 0 & 0 \\
                sin(\alpha) & cos(\alpha) & 0 & 0 \\
                0 & 0 & 1 & 0 \\
                0 & 0 & 0 & 1
            \end{bmatrix} \qquad & R_y & = \begin{bmatrix}
                cos(\beta) & 0 & sin(\beta) & 0 \\
                0 & 1 & 0 & 0 \\
                -sin(\beta) & 0 & cos(\beta) & 0 \\
                0 & 0 & 0 & 1
            \end{bmatrix} \\
            \\
            R_x & = \begin{bmatrix}
                1 & 0 & 0 & 0 \\
                0 & cos(\gamma) & -sin(\gamma) & 0 \\
                0 & sin(\gamma) & cos(\gamma) & 0 \\
                0 & 0 & 0 & 1
            \end{bmatrix} \qquad & T_{\text{xyz}} & = \begin{bmatrix}
                1 & 0 & 0 & \delta x \\
                0 & 1 & 0 & \delta y \\
                0 & 0 & 1 & \delta z \\
                0 & 0 & 0 & 1
            \end{bmatrix}

        The ``transform`` is the combination of these:

        .. math::

            transform = T_{\text{xyz}} \cdot R_z \cdot R_y \cdot R_x = \begin{bmatrix}
                a & b & c & \delta x \\
                d & e & f & \delta y \\
                g & h & i & \delta z \\
                0 & 0 & 0 & 1
            \end{bmatrix}

        Where:

        .. math::

            a & = cos(\alpha) cos(\beta) \\
            b & = cos(\alpha) sin(\beta) sin(\gamma) - sin(\alpha) cos(\gamma) \\
            c & = cos(\alpha) sin(\beta) cos(\gamma) + sin(\alpha) sin(\gamma) \\
            d & = sin(\alpha) cos(\beta) \\
            e & = sin(\alpha) sin(\beta) sin(\gamma) + cos(\alpha) cos(\gamma) \\
            f & = sin(\alpha) sin(\beta) cos(\gamma) - cos(\alpha) sin(\gamma) \\
            g & = -sin(\beta) \\
            h & = cos(\beta) sin(\gamma) \\
            i & = cos(\beta) cos(\gamma)
        """
        # Create reference points at origin
        offset = FreeCAD.Vector(0, 0, 0)
        x_vertex = FreeCAD.Vector(1, 0, 0)  # vertex along +X-axis
        z_vertex = FreeCAD.Vector(0, 0, 1)  # vertex along +Z-axis

        # Transform reference points
        offset = matrix.multiply(offset)
        x_vertex = matrix.multiply(x_vertex)
        z_vertex = matrix.multiply(z_vertex)

        # Get axis vectors (relative to offset vertex)
        x_axis = x_vertex - offset
        z_axis = z_vertex - offset

        # Return new instance
        vect_tuple = lambda v: (v.x, v.y, v.z)
        return cls(
            origin=vect_tuple(offset),
            xDir=vect_tuple(x_axis),
            normal=vect_tuple(z_axis),
        )

    @property
    def world_to_local_transform(self):
        """
        :return: 3d affine transform matrix to convert world coordinates to local coorinates.
        :rtype: :class:`cadquery.Matrix`

        For matrix structure, see :meth:`from_transform`.
        """
        return self.fG

    @property
    def local_to_world_transform(self):
        """
        :return: 3d affine transform matrix to convert local coordinates to world coorinates.
        :rtype: :class:`cadquery.Matrix`

        For matrix structure, see :meth:`from_transform`.
        """
        return self.rG

    def __add__(self, other):
        """
        :return: ``other`` transformed by this coordinate system
        :rtype: that of ``other``
        :raises TypeError: if addition for the given type is not supported

        :class:`CoordSystem` ``A`` + :class:`CoordSystem` ``B``:
        returns world coordinates of ``B`` in ``A``'s coordinates

        """
        if isinstance(other, CoordSystem):
            self_transform = self.local_to_world_transform
            other_transform = other.local_to_world_transform
            return self.from_transform(
                self_transform.multiply(other_transform)
            )
        else:
            raise TypeError("adding a {other_cls:r} to a {self_cls:r} is not supported".format(
                self_cls=type(self),
                other_cls=type(other),
            ))
