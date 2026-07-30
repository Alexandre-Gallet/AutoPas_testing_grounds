/**
 * @file VerletListsLinkedReferencesBase.h
 * @author Alexandre Gallet
 * @date 07.07.2026
 */

#pragma once

#include <cstdint>

#include "algorithm"
#include "autopas/containers/LeavingParticleCollector.h"
#include "autopas/containers/ParticleContainerInterface.h"
#include "autopas/containers/linkedCells/LinkedCellsReferences.h"
#include "autopas/containers/verletListsCellBased/VerletParticleSorting.h"
#include "autopas/utils/ArrayMath.h"
#include "autopas/utils/ParticleCellHelpers.h"
#include "autopas/utils/markParticleAsDeleted.h"

namespace autopas {

/**
 * Base class for Verlet lists which use an underlying linked cells References container.
 * Implementation have to use a constant cutoff radius of the interaction.
 * Cells are created using a cell size of at least cutoff + skin radius.
 * @tparam Particle_T
 */
template <class Particle_T>
class VerletListsLinkedReferencesBase : public ParticleContainerInterface<Particle_T> {
 public:
  /**
   * Type of the Particle.
   */
  using ParticleType = Particle_T;

  /**
   * Type of the ParticleCell used by the underlying linked cells.
   */
  using ParticleCellType = typename LinkedCellsReferences<Particle_T>::ParticleCellType;

  /**
   * ContainerOption used to differentiate VerletLists using LinkedCells vs VerletLists using LinkedCellsReferences
   */
  static constexpr ContainerOption containerOption = ContainerOption::verletListsReferences;

  /**
   * Constructor of the VerletListsLinkedBaseReferences class.
   * The neighbor lists are build using a search radius of cutoff + skin.LinkedParticleCell::Particle_T
   * *rebuildFrequency
   * @param boxMin the lower corner of the domain
   * @param boxMax the upper corner of the domain
   * @param cutoff the cutoff radius of the interaction
   * @param skin   the skin radius
   * @param cellSizeFactor cell size factor relative to cutoff. Verlet lists are only implemented for values >= 1.0
   */
  VerletListsLinkedReferencesBase(const std::array<double, 3> &boxMin, const std::array<double, 3> &boxMax,
                                  const double cutoff, const double skin, const double cellSizeFactor,
                                  const VerletParticleSortingConfig &verletParticleSortingConfig = {})
      : ParticleContainerInterface<Particle_T>(skin),
        _linkedCells(boxMin, boxMax, cutoff, skin, std::max(1.0, cellSizeFactor)),
        _verletParticleSortingConfig(verletParticleSortingConfig) {
    if (cellSizeFactor < 1.0) {
      // Throw exception - this config should have been caught by LogicHandler. Note: This is not a fundamental issue
      // with the algorithm but simply has not been implemented.
      utils::ExceptionHandler::exception(
          "Trying to construct a VerletListsLinkedReferencesBase with CSF < 1.0! This should never occur as the "
          "LogicHandler "
          "should reject this (as Configuration::hasCompatibleValues should return false).");
    }
  }

  void reserve(size_t numParticles, size_t numParticlesHaloEstimate) override {
    _linkedCells.reserve(numParticles, numParticlesHaloEstimate);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::addParticleImpl
   * @note This function invalidates the neighbor lists.
   */
  void addParticleImpl(const Particle_T &p) override {
    _neighborListIsValid.store(false, std::memory_order_relaxed);
    // position is already checked, so call impl directly.
    _linkedCells.addParticleImpl(p);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::addHaloParticleImpl
   * @note This function invalidates the neighbor lists.
   */
  void addHaloParticleImpl(const Particle_T &haloParticle) override {
    _neighborListIsValid.store(false, std::memory_order_relaxed);
    // position is already checked, so call impl directly.
    _linkedCells.addHaloParticleImpl(haloParticle);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::size()
   */
  size_t size() const override { return _linkedCells.size(); }

  /**
   * @copydoc autopas::ParticleContainerInterface::getNumberOfParticles()
   */
  [[nodiscard]] size_t getNumberOfParticles(IteratorBehavior behavior) const override {
    return _linkedCells.getNumberOfParticles(behavior);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::deleteHaloParticles
   * @note This function invalidates the neighbor lists.
   */
  void deleteHaloParticles() override {
    _neighborListIsValid.store(false, std::memory_order_relaxed);
    _linkedCells.deleteHaloParticles();
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::deleteAllParticles
   * @note This function invalidates the neighbor lists.
   */
  void deleteAllParticles() override {
    _neighborListIsValid.store(false, std::memory_order_relaxed);
    _linkedCells.deleteAllParticles();
  }

  std::tuple<const Particle_T *, size_t, size_t> getParticle(size_t cellIndex, size_t particleIndex,
                                                             IteratorBehavior iteratorBehavior,
                                                             const std::array<double, 3> &boxMin,
                                                             const std::array<double, 3> &boxMax) const override {
    return getParticleImpl<true>(cellIndex, particleIndex, iteratorBehavior, boxMin, boxMax);
  }
  std::tuple<const Particle_T *, size_t, size_t> getParticle(size_t cellIndex, size_t particleIndex,
                                                             IteratorBehavior iteratorBehavior) const override {
    // this is not a region iter hence we stretch the bounding box to the numeric max
    constexpr std::array<double, 3> boxMin{std::numeric_limits<double>::lowest(), std::numeric_limits<double>::lowest(),
                                           std::numeric_limits<double>::lowest()};

    constexpr std::array<double, 3> boxMax{std::numeric_limits<double>::max(), std::numeric_limits<double>::max(),
                                           std::numeric_limits<double>::max()};
    return getParticleImpl<false>(cellIndex, particleIndex, iteratorBehavior, boxMin, boxMax);
  }

  /**
   * Container specific implementation for getParticle. See ParticleContainerInterface::getParticle().
   *
   * @tparam regionIter
   * @param cellIndex
   * @param particleIndex
   * @param iteratorBehavior
   * @param boxMin
   * @param boxMax
   * @return tuple<ParticlePointer, CellIndex, ParticleIndex>
   */
  template <bool regionIter>
  std::tuple<const Particle_T *, size_t, size_t> getParticleImpl(size_t cellIndex, size_t particleIndex,
                                                                 IteratorBehavior iteratorBehavior,
                                                                 const std::array<double, 3> &boxMin,
                                                                 const std::array<double, 3> &boxMax) const {
    return _linkedCells.template getParticleImpl<regionIter>(cellIndex, particleIndex, iteratorBehavior, boxMin,
                                                             boxMax);
  }

  bool deleteParticle(Particle_T &particle) override {
    // This function doesn't actually delete anything as it would mess up the references in the lists.
    internal::markParticleAsDeleted(particle);
    return false;
  }

  bool deleteParticle(size_t cellIndex, size_t particleIndex) override {
    // This function doesn't actually delete anything as it would mess up the references in the lists.
    internal::markParticleAsDeleted(this->_linkedCells.getCells()[cellIndex][particleIndex]);
    return false;
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::updateContainer()
   * @note This function invalidates the neighbor lists.
   *
   * If global particle sorting is enabled, the underlying LinkedCellsReferences
   * particle vector is sorted after the normal container update. Sorting happens
   * only on full updates, i.e. when the Verlet lists are allowed to become invalid.
   */
  [[nodiscard]] std::vector<Particle_T> updateContainer(bool keepNeighborListsValid) override {
    if (keepNeighborListsValid) {
      return autopas::LeavingParticleCollector::collectParticlesAndMarkNonOwnedAsDummy(_linkedCells);
    }

    _neighborListIsValid.store(false, std::memory_order_relaxed);

    // First let LinkedCellsReferences handle particles that left the domain,
    // dummy particles, halo particles, and normal reference maintenance.
    auto leavingParticles = _linkedCells.updateContainer(false);

    if (_verletParticleSortingConfig.enabled) {
      // Sorting physically reorders the global ParticleVector and then rebuilds
      // all ReferenceParticleCell pointer lists.
      sortParticlesByConfiguredKey();
    }

    return leavingParticles;
  }

  /**
   * Searches the provided halo particle and updates the found particle.
   * Searches for the provided particle within the halo cells of the container
   * and overwrites the found particle with the provided particle.
   * @param haloParticle
   * @return true if a particle was found and updated, false if it was not found.
   */
  bool updateHaloParticle(const Particle_T &haloParticle) override {
    auto cells = _linkedCells.getCellBlock().getNearbyHaloCells(haloParticle.getR(), this->getVerletSkin());
    for (auto cellptr : cells) {
      bool updated = internal::checkParticleInCellAndUpdateByID(*cellptr, haloParticle);
      if (updated) {
        return true;
      }
    }
    AutoPasLog(TRACE,
               "updateHaloParticle was not able to update particle at "
               "[{}, {}, {}]",
               haloParticle.getR()[0], haloParticle.getR()[1], haloParticle.getR()[2]);
    return false;
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::begin()
   */
  [[nodiscard]] ContainerIterator<Particle_T, true, false> begin(
      IteratorBehavior behavior = IteratorBehavior::ownedOrHalo,
      utils::optRef<typename ContainerIterator<Particle_T, true, false>::ParticleVecType> additionalVectors =
          std::nullopt) override {
    return _linkedCells.begin(behavior, additionalVectors);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::begin()
   */
  [[nodiscard]] ContainerIterator<Particle_T, false, false> begin(
      IteratorBehavior behavior = IteratorBehavior::ownedOrHalo,
      utils::optRef<typename ContainerIterator<Particle_T, false, false>::ParticleVecType> additionalVectors =
          std::nullopt) const override {
    return _linkedCells.begin(behavior, additionalVectors);
  }

  /**
   * @copydoc autopas::LinkedCellsReferences::forEach()
   */
  template <typename Lambda>
  void forEach(Lambda forEachLambda, IteratorBehavior behavior) {
    return _linkedCells.forEach(forEachLambda, behavior);
  }

  /**
   * Iterate over particles in the physical order of the underlying
   * LinkedCellsReferences global ParticleVector.
   *
   * This order is the relevant order after global particle sorting. It is not the
   * same abstraction as normal container iteration, which may be cell-based.
   *
   * @tparam Lambda Callable type accepting Particle_T&.
   * @param forEachLambda Function executed for every particle in storage order.
   */
  template <typename Lambda>
  void forEachParticleInStorageOrder(Lambda forEachLambda) {
    return _linkedCells.forEachParticleInStorageOrder(forEachLambda);
  }

  /**
   * @copydoc autopas::LinkedCellsReferences::reduce()
   */
  template <typename Lambda, typename A>
  void reduce(Lambda reduceLambda, A &result, IteratorBehavior behavior) {
    return _linkedCells.reduce(reduceLambda, result, behavior);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::getRegionIterator()
   */
  [[nodiscard]] ContainerIterator<Particle_T, true, true> getRegionIterator(
      const std::array<double, 3> &lowerCorner, const std::array<double, 3> &higherCorner, IteratorBehavior behavior,
      utils::optRef<typename ContainerIterator<Particle_T, true, true>::ParticleVecType> additionalVectors =
          std::nullopt) override {
    return _linkedCells.getRegionIterator(lowerCorner, higherCorner, behavior, additionalVectors);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::getRegionIterator()
   */
  [[nodiscard]] ContainerIterator<Particle_T, false, true> getRegionIterator(
      const std::array<double, 3> &lowerCorner, const std::array<double, 3> &higherCorner, IteratorBehavior behavior,
      utils::optRef<typename ContainerIterator<Particle_T, false, true>::ParticleVecType> additionalVectors =
          std::nullopt) const override {
    return _linkedCells.getRegionIterator(lowerCorner, higherCorner, behavior, additionalVectors);
  }

  /**
   * @copydoc autopas::LinkedCellsReferences::forEachInRegion()
   */
  template <typename Lambda>
  void forEachInRegion(Lambda forEachLambda, const std::array<double, 3> &lowerCorner,
                       const std::array<double, 3> &higherCorner, IteratorBehavior behavior) {
    _linkedCells.forEachInRegion(forEachLambda, lowerCorner, higherCorner, behavior);
  }

  /**
   * @copydoc autopas::LinkedCellsReferences::reduceInRegion()
   */
  template <typename Lambda, typename A>
  void reduceInRegion(Lambda reduceLambda, A &result, const std::array<double, 3> &lowerCorner,
                      const std::array<double, 3> &higherCorner, IteratorBehavior behavior) {
    _linkedCells.reduceInRegion(reduceLambda, result, lowerCorner, higherCorner, behavior);
  }

  /**
   * Get the dimension of the used cellblock including the haloboxes.
   * @return the dimensions of the used cellblock
   */
  [[nodiscard]] const std::array<std::size_t, 3> &getCellsPerDimension() const {
    return _linkedCells.getCellBlock().getCellsPerDimensionWithHalo();
  }

  /**
   * Generates a traversal selector info for this container.
   * @return Traversal selector info for this container.
   */
  [[nodiscard]] TraversalSelectorInfo getTraversalSelectorInfo() const override {
    return TraversalSelectorInfo(this->_linkedCells.getCellBlock().getCellsPerDimensionWithHalo(),
                                 this->getInteractionLength(), this->_linkedCells.getCellBlock().getCellLength(), 0);
  }

  /**
   * @copydoc autopas::ParticleContainerInterface::getBoxMax()
   */
  [[nodiscard]] const std::array<double, 3> &getBoxMax() const final { return _linkedCells.getBoxMax(); }

  /**
   * @copydoc autopas::ParticleContainerInterface::getBoxMin()
   */
  [[nodiscard]] const std::array<double, 3> &getBoxMin() const final { return _linkedCells.getBoxMin(); }

  /**
   * @copydoc autopas::ParticleContainerInterface::getCutoff()
   */
  [[nodiscard]] double getCutoff() const final { return _linkedCells.getCutoff(); }

  /**
   * @copydoc autopas::ParticleContainerInterface::setCutoff()
   */
  void setCutoff(double cutoff) final { _linkedCells.setCutoff(cutoff); }

  /**
   * @copydoc autopas::ParticleContainerInterface::getVerletSkin()
   */
  [[nodiscard]] double getVerletSkin() const final { return _linkedCells.getVerletSkin(); }

  /**
   * @copydoc autopas::ParticleContainerInterface::getInteractionLength()
   */
  [[nodiscard]] double getInteractionLength() const final { return _linkedCells.getInteractionLength(); }

 private:
  /**
   * Integer coordinate used by the sorting-key encoders.
   *
   * For cell-level sorting this is the 3D linked-cell coordinate.
   * Later, the same type can also represent block coordinates or quantized
   * particle-position coordinates.
   */
  using SortingCoordinate = std::array<uint64_t, 3>;

  /**
   * Number of bits per dimension for particle-level coordinate quantization.
   *
   * In 3D, 21 bits per dimension need 63 bits total for Morton/Hilbert-style
   * keys. This fits into uint64_t while leaving one bit unused.
   */
  static constexpr uint64_t particleSortingBitsPerDimension = 21;

  /**
   * Number of integer grid points per dimension for particle-level sorting.
   *
   * The virtual particle-sorting grid is:
   *
   * 2^21 x 2^21 x 2^21
   */
  static constexpr uint64_t particleSortingGridExtent = uint64_t{1} << particleSortingBitsPerDimension;

  /**
   * Map a particle position to the 3D linked-cell coordinate containing it.
   *
   * This is the coordinate-generation step for resolution == cell.
   *
   * @param position Particle position.
   * @return Integer coordinate of the linked cell containing the position.
   */
  [[nodiscard]] SortingCoordinate getCellCoordinateForPosition(const std::array<double, 3> &position) const {
    const auto cellCoord = _linkedCells.getCellBlock().get3DIndexOfPosition(position);

    return {static_cast<uint64_t>(cellCoord[0]), static_cast<uint64_t>(cellCoord[1]),
            static_cast<uint64_t>(cellCoord[2])};
  }

  /**
   * Get the linked-cell grid dimensions including halo cells.
   *
   * The returned dimensions define the finite grid in which cell-level sorting
   * coordinates live.
   *
   * @return Number of cells per dimension including halo cells.
   */
  [[nodiscard]] SortingCoordinate getCellGridSize() const {
    const auto &cellsPerDim = _linkedCells.getCellBlock().getCellsPerDimensionWithHalo();

    return {static_cast<uint64_t>(cellsPerDim[0]), static_cast<uint64_t>(cellsPerDim[1]),
            static_cast<uint64_t>(cellsPerDim[2])};
  }

  /**
   * Check that all configured block-size components are greater than zero.
   *
   * A zero block-size component would cause division by zero when converting
   * cell coordinates to block coordinates.
   */
  void validateBlockSize() const {
    for (size_t dim = 0; dim < 3; ++dim) {
      if (_verletParticleSortingConfig.blockSize[dim] == 0) {
        utils::ExceptionHandler::exception(
            "VerletListsReferences block-level particle sorting requires positive block-size values. Got "
            "blockSize=[{}, {}, {}].",
            _verletParticleSortingConfig.blockSize[0], _verletParticleSortingConfig.blockSize[1],
            _verletParticleSortingConfig.blockSize[2]);
      }
    }
  }

  /**
   * Compute integer ceil(numerator / denominator).
   *
   * This is used to compute how many blocks are required to cover a cell grid
   * when the number of cells is not exactly divisible by the block size.
   *
   * @param numerator Value to divide.
   * @param denominator Positive divisor.
   * @return Ceiling of numerator / denominator.
   */
  [[nodiscard]] uint64_t ceilDiv(uint64_t numerator, uint64_t denominator) const {
    return (numerator + denominator - 1) / denominator;
  }

  /**
   * Map a particle position to the 3D block coordinate containing it.
   *
   * This is the coordinate-generation step for resolution == block.
   * It first maps the particle position to a linked-cell coordinate and then
   * groups several linked cells into one coarser block.
   *
   * @param position Particle position.
   * @return Integer coordinate of the block containing the particle.
   */
  [[nodiscard]] SortingCoordinate getBlockCoordinateForPosition(const std::array<double, 3> &position) const {
    validateBlockSize();

    const auto cellCoord = getCellCoordinateForPosition(position);

    return {cellCoord[0] / _verletParticleSortingConfig.blockSize[0],
            cellCoord[1] / _verletParticleSortingConfig.blockSize[1],
            cellCoord[2] / _verletParticleSortingConfig.blockSize[2]};
  }

  /**
   * Get the block-grid dimensions.
   *
   * The block grid is derived from the linked-cell grid and the configured
   * block size. If the cell grid is not exactly divisible by the block size,
   * the last block in that dimension contains fewer cells.
   *
   * @return Number of blocks per dimension.
   */
  [[nodiscard]] SortingCoordinate getBlockGridSize() const {
    validateBlockSize();

    const auto cellGridSize = getCellGridSize();

    return {ceilDiv(cellGridSize[0], _verletParticleSortingConfig.blockSize[0]),
            ceilDiv(cellGridSize[1], _verletParticleSortingConfig.blockSize[1]),
            ceilDiv(cellGridSize[2], _verletParticleSortingConfig.blockSize[2])};
  }

  /**
   * Get the virtual particle-level sorting grid dimensions.
   *
   * Particle-level sorting quantizes continuous particle positions into a
   * power-of-two integer grid. The same grid is used for linear, Morton, and
   * Hilbert order.
   *
   * @return Virtual grid dimensions for particle-level sorting.
   */
  [[nodiscard]] SortingCoordinate getParticleGridSize() const {
    return {particleSortingGridExtent, particleSortingGridExtent, particleSortingGridExtent};
  }

  /**
   * Quantize a particle position into the virtual particle-level sorting grid.
   *
   * This is the coordinate-generation step for resolution == particle.
   *
   * Each coordinate is mapped as:
   *
   * relative = (position - boxMin) / (boxMax - boxMin)
   * clamped  = clamp(relative, 0, 1)
   * coord    = floor(clamped * (gridExtent - 1))
   *
   * This produces integer coordinates in:
   *
   * [0, particleSortingGridExtent - 1]^3
   *
   * @param position Particle position.
   * @return Quantized integer coordinate of the particle position.
   */
  [[nodiscard]] SortingCoordinate getParticleCoordinateForPosition(const std::array<double, 3> &position) const {
    constexpr uint64_t maxCoordinate = particleSortingGridExtent - 1;

    SortingCoordinate coord{};

    for (size_t dim = 0; dim < 3; ++dim) {
      const double boxLength = this->getBoxMax()[dim] - this->getBoxMin()[dim];

      // Degenerate boxes should not occur in normal simulations, but if they do,
      // place all particles at coordinate 0 in that dimension.
      const double relativePosition = boxLength > 0. ? (position[dim] - this->getBoxMin()[dim]) / boxLength : 0.;

      // Clamp to make the key generation robust for particles exactly on or
      // slightly beyond the box boundary due to floating-point roundoff.
      const double clampedRelativePosition = std::clamp(relativePosition, 0., 1.);

      coord[dim] = static_cast<uint64_t>(clampedRelativePosition * static_cast<double>(maxCoordinate));
    }

    return coord;
  }

  /**
   * Encode a 3D coordinate using x-fastest row-major linear indexing.
   *
   * Formula:
   *
   * key = x + nx * (y + ny * z)
   *
   * @param coord 3D coordinate.
   * @param gridSize Grid dimensions.
   * @return Linear sorting key.
   */
  [[nodiscard]] uint64_t linearKey(const SortingCoordinate &coord, const SortingCoordinate &gridSize) const {
    return coord[0] + gridSize[0] * (coord[1] + gridSize[1] * coord[2]);
  }

  /**
   * Return the number of bits needed to represent values up to maxValue.
   *
   * Example:
   * maxValue = 0 -> 1 bit
   * maxValue = 1 -> 1 bit
   * maxValue = 2 -> 2 bits
   * maxValue = 7 -> 3 bits
   *
   * @param maxValue Largest value that must be representable.
   * @return Number of bits required.
   */
  [[nodiscard]] unsigned int bitsNeeded(uint64_t maxValue) const {
    unsigned int bits = 0;
    do {
      ++bits;
      maxValue >>= 1;
    } while (maxValue > 0);

    return bits;
  }

  /**
   * Return the number of bits needed for all coordinates in a grid.
   *
   * Morton and Hilbert encoders operate on a virtual power-of-two cube.
   * If the real grid has dimensions [53, 31, 37], this function returns
   * the number of bits needed for the largest coordinate, so the virtual
   * encoding cube becomes 64 x 64 x 64.
   *
   * @param gridSize Real grid dimensions.
   * @return Bits per dimension for the virtual encoding grid.
   */
  [[nodiscard]] unsigned int bitsNeededForGrid(const SortingCoordinate &gridSize) const {
    const auto maxGridExtent = std::max({gridSize[0], gridSize[1], gridSize[2]});
    return bitsNeeded(maxGridExtent - 1);
  }

  /**
   * Encode a 3D coordinate using Morton/Z-order bit interleaving.
   *
   * The bits of x, y, and z are interleaved:
   *
   * x0 y0 z0 x1 y1 z1 ...
   *
   * @param coord 3D integer coordinate.
   * @param bitsPerDimension Number of coordinate bits to encode per dimension.
   * @return Morton sorting key.
   */
  [[nodiscard]] uint64_t mortonKey(const SortingCoordinate &coord, unsigned int bitsPerDimension) const {
    uint64_t mortonIndex = 0;

    for (uint64_t bit = 0; bit < bitsPerDimension; ++bit) {
      // Place bit 'bit' of x into Morton bit 3 * bit.
      mortonIndex |= ((coord[0] & (uint64_t{1} << bit)) << (2 * bit));

      // Place bit 'bit' of y into Morton bit 3 * bit + 1.
      mortonIndex |= ((coord[1] & (uint64_t{1} << bit)) << (2 * bit + 1));

      // Place bit 'bit' of z into Morton bit 3 * bit + 2.
      mortonIndex |= ((coord[2] & (uint64_t{1} << bit)) << (2 * bit + 2));
    }

    return mortonIndex;
  }

  /**
   * Transform 3D integer coordinates into Hilbert transpose form.
   *
   * This is the coordinate transform used by John Skilling's Hilbert curve
   * algorithm. The input coordinate is modified in-place. After this transform,
   * the bits of the three coordinates can be read out to form a Hilbert index.
   *
   * @param coord Coordinate to transform in-place.
   * @param bitsPerDimension Number of coordinate bits per dimension.
   */
  void hilbertAxesToTranspose(SortingCoordinate &coord, unsigned int bitsPerDimension) const {
    if (bitsPerDimension == 0) {
      return;
    }

    const uint64_t highestBit = uint64_t{1} << (bitsPerDimension - 1);

    // Inverse undo step from Skilling's algorithm. This performs the rotations
    // and reflections that make the Hilbert curve continuous across subcubes.
    for (uint64_t q = highestBit; q > 1; q >>= 1) {
      const uint64_t p = q - 1;

      for (size_t dim = 0; dim < 3; ++dim) {
        if ((coord[dim] & q) != 0) {
          coord[0] ^= p;
        } else {
          const uint64_t t = (coord[0] ^ coord[dim]) & p;
          coord[0] ^= t;
          coord[dim] ^= t;
        }
      }
    }

    // Gray encode the coordinate axes.
    for (size_t dim = 1; dim < 3; ++dim) {
      coord[dim] ^= coord[dim - 1];
    }

    uint64_t t = 0;
    for (uint64_t q = highestBit; q > 1; q >>= 1) {
      if ((coord[2] & q) != 0) {
        t ^= q - 1;
      }
    }

    // Apply the final prefix transform to all dimensions.
    for (size_t dim = 0; dim < 3; ++dim) {
      coord[dim] ^= t;
    }
  }

  /**
   * Encode a 3D coordinate using Hilbert order.
   *
   * The real grid is embedded into a virtual power-of-two cube determined by
   * bitsPerDimension. The returned key can be used for sorting particles along
   * a 3D Hilbert curve.
   *
   * @param coord 3D integer coordinate.
   * @param bitsPerDimension Number of coordinate bits to encode per dimension.
   * @return Hilbert sorting key.
   */
  [[nodiscard]] uint64_t hilbertKey(SortingCoordinate coord, unsigned int bitsPerDimension) const {
    hilbertAxesToTranspose(coord, bitsPerDimension);

    uint64_t key = 0;

    // Read the transformed coordinate bits from most significant to least
    // significant. This packs the Hilbert transpose into one sortable integer.
    for (int bit = static_cast<int>(bitsPerDimension) - 1; bit >= 0; --bit) {
      for (size_t dim = 0; dim < 3; ++dim) {
        key = (key << 1) | ((coord[dim] >> bit) & uint64_t{1});
      }
    }

    return key;
  }

  /**
   * Compute the configured sorting key for one particle.
   *
   * The function first generates an integer coordinate according to the selected
   * sorting resolution. It then encodes that coordinate with the selected
   * sorting order.
   *
   * Currently supported resolutions:
   *
   * - cell:
   *   particle position -> linked-cell coordinate
   *
   * - block:
   *   particle position -> linked-cell coordinate -> block coordinate
   *
   * - particle:
   *   particle position -> quantized integer coordinate
   *
   * @param particle Particle for which a key should be generated.
   * @return Sorting key according to the current config.
   */
  [[nodiscard]] uint64_t sortingKeyForParticle(const Particle_T &particle) const {
    SortingCoordinate coord{};
    SortingCoordinate gridSize{};

    switch (_verletParticleSortingConfig.resolution) {
      case VerletParticleSortingResolution::cell:
        coord = getCellCoordinateForPosition(particle.getR());
        gridSize = getCellGridSize();
        break;

      case VerletParticleSortingResolution::block:
        coord = getBlockCoordinateForPosition(particle.getR());
        gridSize = getBlockGridSize();
        break;

      case VerletParticleSortingResolution::particle:
        coord = getParticleCoordinateForPosition(particle.getR());
        gridSize = getParticleGridSize();
        break;
    }

    switch (_verletParticleSortingConfig.order) {
      case VerletParticleSortingOrder::linear:
        return linearKey(coord, gridSize);

      case VerletParticleSortingOrder::morton:
        return mortonKey(coord, bitsNeededForGrid(gridSize));

      case VerletParticleSortingOrder::hilbert:
        return hilbertKey(coord, bitsNeededForGrid(gridSize));
    }

    utils::ExceptionHandler::exception("Unknown Verlet particle sorting order.");
    return 0;
  }

  /**
   * Sort the global LinkedCellsReferences particle storage using the configured key.
   *
   * The primary key is generated from the configured resolution and order.
   * Particle id is used as a deterministic final tie breaker.
   */
  void sortParticlesByConfiguredKey() {
    _linkedCells.sortParticlesAndUpdateReferences([this](const Particle_T &a, const Particle_T &b) {
      const auto keyA = sortingKeyForParticle(a);
      const auto keyB = sortingKeyForParticle(b);

      if (keyA != keyB) {
        return keyA < keyB;
      }

      // Deterministic tiebreaker for particles with identical sorting keys.
      return a.getID() < b.getID();
    });
  }

 protected:
  /// internal linked cells storage, handles Particle storage and used to build verlet lists
  LinkedCellsReferences<Particle_T> _linkedCells;

  /// specifies if the neighbor list is currently valid
  std::atomic<bool> _neighborListIsValid{false};

  /// specifies if the current verlet list was built for newton3
  bool _verletBuiltNewton3{false};

  /// specifies sorting order and resolution
  VerletParticleSortingConfig _verletParticleSortingConfig{};
};

}  // namespace autopas
