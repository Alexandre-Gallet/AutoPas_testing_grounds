/**
 * @file VerletParticleSorting.h
 * @author Alexandre Gallet
 * @date 07.07.2026
 */

#pragma once

#include <array>
#include <string>

// TODO: Integrate this into Option<> to later use autoTuning for selecting best resolution and sorting strategy during
// simulation.
namespace autopas {

/**
 * Spatial resolution at which the global particle vector should be sorted.
 *
 * block:
 *   Group multiple linked cells into one coarse block and sort by block coordinate.
 *
 * cell:
 *   Sort by the linked cell a particle belongs to.
 *
 * particle:
 *   Sort by a quantized particle position, i.e. finer than cell resolution.
 */
enum class VerletParticleSortingResolution {
  block,
  cell,
  particle,
};

/**
 * Ordering strategy used for the selected sorting resolution.
 *
 * linear:
 *   Use x-fastest linear indexing.
 *
 * morton:
 *   Use Morton / Z-order indexing.
 *
 * hilbert:
 *   Use Hilbert curve indexing.
 */
enum class VerletParticleSortingOrder {
  linear,
  morton,
  hilbert,
};

/**
 * Configuration for global particle sorting in VerletListsReferences.
 *
 * This only describes which sorting should be applied. The actual sorting is
 * performed by the VerletListsReferences backend during container update /
 * Verlet-list rebuild.
 */
struct VerletParticleSortingConfig {
  /**
   * If false, no global particle sorting is applied.
   */
  bool enabled{false};

  /**
   * Spatial resolution used to generate sorting keys.
   */
  VerletParticleSortingResolution resolution{VerletParticleSortingResolution::cell};

  /**
   * Ordering strategy used for the selected resolution.
   */
  VerletParticleSortingOrder order{VerletParticleSortingOrder::linear};

  /**
   * Number of linked cells per block in x, y, and z direction.
   *
   * Only used if resolution == block.
   */
  std::array<unsigned long, 3> blockSize{4, 4, 4};

  /**
   * Needed because this config is stored in ContainerSelectorInfo, where
   * changes to the config should be detectable.
   */
  bool operator==(const VerletParticleSortingConfig &other) const {
    return enabled == other.enabled and resolution == other.resolution and order == other.order and
           blockSize == other.blockSize;
  }

  bool operator!=(const VerletParticleSortingConfig &other) const { return not(*this == other); }
};

/**
 * Convert sorting resolution to a human-readable string for logging.
 */
inline std::string to_string(VerletParticleSortingResolution resolution) {
  switch (resolution) {
    case VerletParticleSortingResolution::block:
      return "block";
    case VerletParticleSortingResolution::cell:
      return "cell";
    case VerletParticleSortingResolution::particle:
      return "particle";
  }
  return "unknown";
}

/**
 * Convert sorting order to a human-readable string for logging.
 */
inline std::string to_string(VerletParticleSortingOrder order) {
  switch (order) {
    case VerletParticleSortingOrder::linear:
      return "linear";
    case VerletParticleSortingOrder::morton:
      return "morton";
    case VerletParticleSortingOrder::hilbert:
      return "hilbert";
  }
  return "unknown";
}

}  // namespace autopas
