"""Cave solver example."""

import grilops
import grilops.regions
import grilops.sightlines


SYM = grilops.SymbolSet([("B", chr(0x2588)), ("W", " ")])
HEIGHT, WIDTH = 10, 10
GIVENS = [
    [6, 0, 0, 0, 6, 0, 0, 0, 0, 4],
    [0, 0, 0, 0, 0, 6, 0, 0, 0, 0],
    [0, 0, 3, 0, 0, 0, 0, 5, 0, 0],
    [0, 0, 0, 7, 0, 0, 9, 0, 0, 0],
    [0, 5, 0, 0, 3, 0, 0, 0, 0, 5],
    [5, 0, 0, 0, 0, 5, 0, 0, 2, 0],
    [0, 0, 0, 2, 0, 0, 4, 0, 0, 0],
    [0, 0, 7, 0, 0, 0, 0, 4, 0, 0],
    [0, 0, 0, 0, 2, 0, 0, 0, 0, 0],
    [5, 0, 0, 0, 0, 6, 0, 0, 0, 6],
]


def main():
  """Cave solver example."""
  sg = grilops.SymbolGrid(HEIGHT, WIDTH, SYM)
  rc = grilops.regions.RegionConstrainer(HEIGHT, WIDTH, btor=sg.btor)

  # The cave must be a single connected group. We'll define a variable to keep
  # track of its region ID.
  cave_region_id = sg.btor.Var(
      sg.btor.BitVecSort(rc.region_id_grid[0][0].width), "cave_region_id")

  for y in range(HEIGHT):
    for x in range(WIDTH):
      # Ensure that every cave cell has the same region ID.
      sg.btor.Assert(
          sg.cell_is(y, x, SYM.W) ==
          (rc.region_id_grid[y][x] == cave_region_id)
      )

      # Every shaded region must connect to an edge of the grid. We'll enforce
      # this by requiring that the root of a shaded region is along the edge of
      # the grid.
      if 0 < y < HEIGHT - 1 and 0 < x < WIDTH - 1:
        sg.btor.Assert(
            sg.btor.Implies(
                sg.cell_is(y, x, SYM.B),
                rc.parent_grid[y][x] != grilops.regions.R
            )
        )

  for y in range(HEIGHT):
    for x in range(WIDTH):
      if GIVENS[y][x] == 0:
        continue
      sg.btor.Assert(sg.cell_is(y, x, SYM.W))
      # Count the cells visible along sightlines from the given cell.
      visible_cell_count, overflow = sg.btor.UAddDetectOverflow(*([
          grilops.sightlines.count_cells(
              sg, n.location, n.direction, stop=lambda c: c == SYM.B,
              count_bit_width=sg.btor.BitWidthFor(HEIGHT + WIDTH)
          ) for n in sg.adjacent_cells(y, x)
      ] + [1]))
      sg.btor.Assert(sg.btor.Not(overflow))
      sg.btor.Assert(visible_cell_count == GIVENS[y][x])

  def print_grid():
    sg.print(lambda y, x, _: str(GIVENS[y][x]) if GIVENS[y][x] != 0 else None)

  if sg.solve():
    print_grid()
    print()
    if sg.is_unique():
      print("Unique solution")
    else:
      print("Alternate solution")
      print_grid()
  else:
    print("No solution")


if __name__ == "__main__":
  main()
