"""This module supports puzzles that group cells into contiguous regions.

Internally, the #RegionConstrainer constructs subtrees, each spanning the cells
contained within a region. Aspects of a cell's relationship to the other cells
in its subtree are exposed by properties of the #RegionConstrainer.
"""

from typing import Dict, Optional
from z3 import And, ArithRef, If, Implies, Int, Or, Solver, Sum  # type: ignore

from .geometry import Lattice, Point, Vector


class RegionConstrainer:  # pylint: disable=R0902
  """Creates constraints for grouping cells into contiguous regions.

  # Arguments
  locations (Lattice): Lattice of locations in the grid.
  solver (z3.Solver, None): A #Solver object. If None, a #Solver will be
      constructed.
  complete (bool): If true, every cell must be part of a region. Defaults to
      true.
  min_region_size(int, None): The minimum possible size of a region.
  max_region_size(int, None): The maximum possible size of a region.
  """
  _instance_index = 0

  def __init__(  # pylint: disable=R0913
      self,
      locations: Lattice,
      solver: Solver = None,
      complete: bool = True,
      min_region_size: Optional[int] = None,
      max_region_size: Optional[int] = None
  ):
    RegionConstrainer._instance_index += 1
    self.__lattice = locations
    if solver:
      self.__solver = solver
    else:
      self.__solver = Solver()
    self.__complete = complete
    if min_region_size is not None:
      self.__min_region_size = min_region_size
    else:
      self.__min_region_size = 1
    if max_region_size is not None:
      self.__max_region_size = max_region_size
    else:
      self.__max_region_size = len(self.__lattice.points)
    self.__manage_adjacencies()
    self.__create_grids()
    self.__add_constraints()

  def __manage_adjacencies(self):
    """Creates the structures used for managing adjacencies.

    Ccreates the mapping between adjacency directions and the parent
    indices corresponding to them.
    """
    self.__adjacency_directions = self.__lattice.adjacency_directions()
    self.__adjacency_to_index = dict(
        (v, index + 2) for index, v in enumerate(self.__adjacency_directions)
    )
    self.__parent_type_to_index = {}
    self.__parent_types = []
    for name in ["X", "R"] + self.__lattice.adjacency_direction_names():
      index = len(self.__parent_types)
      self.__parent_type_to_index[name] = index
      self.__parent_types.append(name)

  def __create_grids(self):
    """Create the grids used to model region constraints."""
    locations = self.__lattice.points
    self.__parent_grid: Dict[Point, ArithRef] = {}
    for p in locations:
      v = Int(f"rcp-{RegionConstrainer._instance_index}-{p.y}-{p.x}")
      if self.__complete:
        self.__solver.add(v >= self.parent_type_to_index("R"))
      else:
        self.__solver.add(v >= self.parent_type_to_index("X"))
      self.__solver.add(v <= len(self.__adjacency_directions) + 1)
      self.__parent_grid[p] = v

    self.__subtree_size_grid: Dict[Point, ArithRef] = {}
    for p in locations:
      v = Int(f"rcss-{RegionConstrainer._instance_index}-{p.y}-{p.x}")
      if self.__complete:
        self.__solver.add(v >= 1)
      else:
        self.__solver.add(v >= 0)
      self.__solver.add(v <= self.__max_region_size)
      self.__subtree_size_grid[p] = v

    self.__region_id_grid: Dict[Point, ArithRef] = {}
    for p in locations:
      v = Int(f"rcid-{RegionConstrainer._instance_index}-{p.y}-{p.x}")
      if self.__complete:
        self.__solver.add(v >= 0)
      else:
        self.__solver.add(v >= -1)
      self.__solver.add(v < len(locations))
      parent = self.__parent_grid[p]
      self.__solver.add(Implies(
          parent == self.parent_type_to_index("X"),
          v == -1
      ))
      self.__solver.add(Implies(
          parent == self.parent_type_to_index("R"),
          v == self.__lattice.point_to_index(p)
      ))
      self.__region_id_grid[p] = v

    self.__region_size_grid: Dict[Point, ArithRef] = {}
    for p in locations:
      v = Int(f"rcrs-{RegionConstrainer._instance_index}-{p.y}-{p.x}")
      if self.__complete:
        self.__solver.add(v >= self.__min_region_size)
      else:
        self.__solver.add(Or(v >= self.__min_region_size, v == -1))
      self.__solver.add(v <= self.__max_region_size)
      parent = self.__parent_grid[p]
      subtree_size = self.__subtree_size_grid[p]
      self.__solver.add(Implies(
          parent == self.parent_type_to_index("X"),
          v == -1
      ))
      self.__solver.add(Implies(
          parent == self.parent_type_to_index("R"),
          v == subtree_size
      ))
      self.__region_size_grid[p] = v

  def __add_constraints(self):
    """Add constraints to the region modeling grids."""
    def constrain_side(p, sp, sd):
      self.__solver.add(Implies(
          self.__parent_grid[p] == self.parent_type_to_index("X"),
          self.__parent_grid[sp] != sd
      ))
      self.__solver.add(Implies(
          self.__parent_grid[sp] == sd,
          And(
              self.__region_id_grid[p] == self.__region_id_grid[sp],
              self.__region_size_grid[p] == self.__region_size_grid[sp],
          )
      ))

    def subtree_size_term(sp, sd):
      return If(
          self.__parent_grid[sp] == sd,
          self.__subtree_size_grid[sp],
          0
      )

    for p in self.__lattice.points:
      parent = self.__parent_grid[p]
      subtree_size_terms = [
          If(parent != self.parent_type_to_index("X"), 1, 0)
      ]

      for d in self.__adjacency_directions:
        sp = p.translate(d)
        if sp in self.__parent_grid:
          opposite_index = self.__adjacency_to_index[d.negate()]
          constrain_side(p, sp, opposite_index)
          subtree_size_terms.append(subtree_size_term(sp, opposite_index))
        else:
          d_index = self.__adjacency_to_index[d]
          self.__solver.add(parent != d_index)

      self.__solver.add(
          self.__subtree_size_grid[p] == Sum(*subtree_size_terms)
      )

  def location_to_region_id(self, location: Point) -> Optional[int]:
    """Returns the region root ID for a grid location.

    # Arguments
    location (Point): The grid location.

    # Returns
    (Optional[int]): The region ID.
    """
    return self.__lattice.point_to_index(location)

  def region_id_to_location(self, region_id: int) -> Point:
    """Returns the grid location for a region root ID.

    # Arguments
    region_id (int): The region ID.

    # Returns
    (Point): The (y, x) grid location.
    """
    return self.__lattice.points[region_id]

  def adjacency_to_index(self, direction: Vector) -> int:
    """Returns the parent_grid value corresponding to the given direction.
    For instance, if direction is (-1, 0), return the index for N.

    # Arguments:
    direction (Vector): The direction of adjacency.

    # Returns
    (int): The parent_grid value that means that the parent in its region's
        subtree is the cell offset by that direction.
    """
    return self.__adjacency_to_index[direction]

  def parent_type_to_index(self, parent_type: str) -> int:
    """Returns the parent_grid value corresponding to the given parent type.

    # Arguments:
    parent_type (str): The parent type.

    # Returns:
    (int): The corresponding parent_grid value.
    """
    return self.__parent_type_to_index[parent_type]

  @property
  def solver(self) -> Solver:
    """(z3.Solver): The #Solver associated with this #RegionConstrainer."""
    return self.__solver

  @property
  def region_id_grid(self) -> Dict[Point, ArithRef]:
    """(Dict[Point, ArithRef]): A dictionary of numbers identifying regions.

    A region's identifier is the position in the grid (going in order from left
    to right, top to bottom) of the root of that region's subtree.
    """
    return self.__region_id_grid

  @property
  def region_size_grid(self) -> Dict[Point, ArithRef]:
    """(Dict[Point, ArithRef]): A dictionary of region sizes."""
    return self.__region_size_grid

  @property
  def parent_grid(self) -> Dict[Point, ArithRef]:
    """(Dict[Point, ArithRef]): A dictionary of region subtree parent pointers."""
    return self.__parent_grid

  @property
  def subtree_size_grid(self) -> Dict[Point, ArithRef]:
    """(Dict[Point, ArithRef]): A dictionary of cell subtree sizes.

    A cell's subtree size is one plus the number of cells that are descendents
    of the cell in its region's subtree.
    """
    return self.__subtree_size_grid

  def print_trees(self):
    """Prints the region parent assigned to each cell.

    Should be called only after the solver has been checked.
    """
    labels = {
        "X": " ",
        "R": "R",
        "N": chr(0x25B4),
        "E": chr(0x25B8),
        "S": chr(0x25BE),
        "W": chr(0x25C2),
        "NE" : chr(0x2B67),
        "NW" : chr(0x2B66),
        "SE" : chr(0x2B68),
        "SW" : chr(0x2B69),
    }

    model = self.__solver.model()

    def print_function(p):
      v = self.__parent_grid[p]
      parent_index = model.eval(v).as_long()
      parent_type = self.__parent_types[parent_index]
      return labels[parent_type]

    self.__lattice.print(print_function, " ")

  def print_subtree_sizes(self):
    """Prints the region subtree size of each cell.

    Should be called only after the solver has been checked.
    """
    model = self.__solver.model()
    def print_function(p):
      v = self.__subtree_size_grid[p]
      value = model.eval(v).as_long()
      return f"{value:3}"

    self.__lattice.print(print_function, "   ")

  def print_region_ids(self):
    """Prints a number identifying the region that owns each cell.

    Should be called only after the solver has been checked.
    """
    model = self.__solver.model()
    def print_function(p):
      v = self.__region_id_grid[p]
      value = model.eval(v).as_long()
      return f"{value:3}"

    self.__lattice.print(print_function, "   ")

  def print_region_sizes(self):
    """Prints the size of the region that contains each cell.

    Should be called only after the solver has been checked.
    """
    model = self.__solver.model()
    def print_function(p):
      v = self.__region_size_grid[p]
      value = model.eval(v).as_long()
      return f"{value:3}"

    self.__lattice.print(print_function, "   ")
