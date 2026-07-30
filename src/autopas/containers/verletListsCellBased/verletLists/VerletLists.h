/**
 * @file VerletLists.h
 * @author seckler
 * @date 19.04.18
 */

#pragma once

#include "VerletListHelpers.h"
#include "autopas/containers/CellBasedParticleContainer.h"
#include "autopas/containers/linkedCells/LinkedCells.h"
#include "autopas/containers/linkedCells/traversals/LCC08Traversal.h"
#include "autopas/containers/verletListsCellBased/VerletListsLinkedBase.h"
#include "autopas/containers/verletListsCellBased/VerletListsLinkedReferencesBase.h"
#include "autopas/containers/verletListsCellBased/VerletParticleSorting.h"
#include "autopas/containers/verletListsCellBased/verletLists/traversals/VLListIterationTraversal.h"
#include "autopas/containers/verletListsCellBased/verletLists/traversals/VLTraversalInterface.h"
#include "autopas/options/DataLayoutOption.h"
#include "autopas/utils/ArrayMath.h"
#include "autopas/utils/StaticBoolSelector.h"

namespace autopas {

/**
 * Verlet Lists container.
 * The VerletLists class uses neighborhood lists to calculate pairwise
 * interactions of particles.
 * It is optimized for a constant, i.e. particle independent, cutoff radius of
 * the interaction.
 * Cells are created using a cell size of at least cutoff + skin radius.
 * @tparam Particle_T
 * @tparam LinkedCellsBackend_T backend used for linked-cells i.e. linkedcells vs linkedcells references
 */
template <class Particle_T, template <class> class LinkedCellsBackend_T = VerletListsLinkedBase>
class VerletLists : public LinkedCellsBackend_T<Particle_T> {
  /**
   * Type of the Particle.
   */
  using ParticleType = Particle_T;
  /**
   * Alias for linked cells backend type
   */
  using BackendType = LinkedCellsBackend_T<Particle_T>;
  /**
   * Type of the ParticleCell used by the underlying linked cells backend.
   */
  using ParticleCellType = typename BackendType::ParticleCellType;

 public:
  /**
   * Enum that specifies how the verlet lists should be build
   */
  enum BuildVerletListType {
    /**
     * Build it using AoS
     */
    VerletAoS,
    /**
     * Build it using AoS
     */
    VerletSoA,
  };

  /**
   * Constructor of the VerletLists class.
   * The neighbor lists are build using a search radius of cutoff + skin.
   * @param boxMin The lower corner of the domain.
   * @param boxMax The upper corner of the domain.
   * @param cutoff The cutoff radius of the interaction.
   * @param skin The skin radius per timestep.
   * @param buildVerletListType Specifies how the verlet list should be build, see BuildVerletListType
   * @param cellSizeFactor cell size factor ralative to cutoff
   */
  VerletLists(const std::array<double, 3> &boxMin, const std::array<double, 3> &boxMax, const double cutoff,
              const double skin, const BuildVerletListType buildVerletListType = BuildVerletListType::VerletSoA,
              const double cellSizeFactor = 1.0, const VerletParticleSortingConfig &verletParticleSortingConfig = {})
      : BackendType(boxMin, boxMax, cutoff, skin, cellSizeFactor, verletParticleSortingConfig),
        _buildVerletListType(buildVerletListType) {}

  /**
   * @copydoc ParticleContainerInterface::getContainerType()
   */
  [[nodiscard]] ContainerOption getContainerType() const override { return BackendType::containerOption; }

  void computeInteractions(TraversalInterface *traversal) override {
    // Check if traversal is allowed for this container and give it the data it needs.
    auto *verletTraversalInterface = dynamic_cast<VLTraversalInterface<ParticleCellType> *>(traversal);
    if (verletTraversalInterface) {
      verletTraversalInterface->setCellsAndNeighborLists(this->_linkedCells.getCells(), _aosNeighborLists,
                                                         _soaNeighborLists, &_soaParticleOrder);

    } else {
      utils::ExceptionHandler::exception("trying to use a traversal of wrong type in VerletLists::computeInteractions");
    }

    traversal->initTraversal();
    traversal->traverseParticles();
    traversal->endTraversal();
  }

  /**
   * get the actual neighbor list
   * @return the neighbor list
   */
  typename VerletListHelpers<Particle_T>::NeighborListAoSType &getVerletListsAoS() { return _aosNeighborLists; }

  /**
   * Rebuilds the verlet lists, marks them valid and resets the internal counter.
   * @note This function will be called in computeInteractions()!
   * @param traversal
   */
  void rebuildNeighborLists(TraversalInterface *traversal) override {
    this->_verletBuiltNewton3 = traversal->getUseNewton3();
    this->updateVerletListsAoS(traversal->getUseNewton3());
    // the neighbor list is now valid
    this->_neighborListIsValid.store(true, std::memory_order_relaxed);

    if (not _soaListIsValid and traversal->getDataLayout() == DataLayoutOption::soa) {
      // only do this if we need it, i.e., if we are using soa!
      generateSoAListFromAoSVerletLists();
    }
  }

 protected:
  /**
   * True if this VerletLists instantiation uses ReferenceParticleCell.
   *
   * The sorted global SoA order only makes sense for the LinkedCellsReferences
   * backend, because only that backend stores particles in one global
   * ParticleVector. Normal LinkedCells stores particles inside individual cells.
   */
  static constexpr bool usesReferenceParticleCells =
      std::is_same_v<ParticleCellType, ReferenceParticleCell<Particle_T>>;

  /**
   * True if this container should build an explicit sorted SoA particle order.
   *
   * For now this only describes the intended path. The order is generated in this
   * step but not used for SoA loading or SoA neighbor-list conversion yet.
   */
  [[nodiscard]] bool shouldUseSortedSoAParticleOrder() const {
    if constexpr (usesReferenceParticleCells) {
      return this->_verletParticleSortingConfig.enabled;
    } else {
      return false;
    }
  }

  /**
   * Update the verlet lists for AoS usage
   * @param useNewton3
   */
  virtual void updateVerletListsAoS(bool useNewton3) {
    generateAoSNeighborLists();
    typename VerletListHelpers<Particle_T>::VerletListGeneratorFunctor f(_aosNeighborLists,
                                                                         this->getCutoff() + this->getVerletSkin());

    /// @todo autotune traversal
    DataLayoutOption dataLayout;
    if (_buildVerletListType == BuildVerletListType::VerletAoS) {
      dataLayout = DataLayoutOption::aos;
    } else if (_buildVerletListType == BuildVerletListType::VerletSoA) {
      dataLayout = DataLayoutOption::soa;
    } else {
      utils::ExceptionHandler::exception("VerletLists::updateVerletListsAoS(): unsupported BuildVerletListType: {}",
                                         static_cast<int>(_buildVerletListType));
    }
    auto traversal =
        LCC08Traversal<ParticleCellType, typename VerletListHelpers<Particle_T>::VerletListGeneratorFunctor>(
            this->_linkedCells.getCellBlock().getCellsPerDimensionWithHalo(), f, this->getInteractionLength(),
            this->_linkedCells.getCellBlock().getCellLength(), dataLayout, useNewton3);
    this->_linkedCells.computeInteractions(&traversal);

    _soaListIsValid = false;
  }

  /**
   * Clears and then generates the AoS neighbor lists.
   * The Id Map is used to map the id of a particle to the actual particle.
   * @return Number of particles in the container
   */
  size_t generateAoSNeighborLists() {
    size_t numParticles = 0;
    _aosNeighborLists.clear();
    // DON'T simply parallelize this loop!!! this needs modifications if you want to parallelize it!
    // We have to iterate also over dummy particles here to ensure a correct size of the arrays.
    for (auto iter = this->begin(IteratorBehavior::ownedOrHaloOrDummy); iter.isValid(); ++iter, ++numParticles) {
      // create the verlet list entries for all particles
      _aosNeighborLists[&(*iter)];
    }

    return numParticles;
  }

  /**
   * Build the explicit particle order that should define SoA indices.
   *
   * For the references backend, this order follows the physical storage order of
   * the global ParticleVector. After global particle sorting, this is the sorted
   * particle order.
   *
   * This helper only prepares the order. It does not yet change how _soa is
   * loaded or how _soaNeighborLists are generated.
   */
  void generateSoAParticleOrderFromStorageOrder() {
    _soaParticleOrder.clear();

    if constexpr (usesReferenceParticleCells) {
      if (shouldUseSortedSoAParticleOrder()) {
        _soaParticleOrder.reserve(_aosNeighborLists.size());

        this->forEachParticleInStorageOrder([this](Particle_T &particle) {
          // Store the address of the particle in the sorted global ParticleVector.
          // Later, the vector index will become the SoA index of this particle.
          _soaParticleOrder.push_back(&particle);
        });
      }
    }
  }

  /**
   * Fills SoA neighbor list with particle indices.
   */
  void generateSoAListFromAoSVerletLists() {
    // Prepare the explicit sorted SoA particle order if this is the references
    // backend and particle sorting is enabled.
    generateSoAParticleOrderFromStorageOrder();

    // resize the list to the size of the aos neighborlist
    _soaNeighborLists.resize(_aosNeighborLists.size());
    // clear the aos 2 soa map
    _particlePtr2indexMap.clear();

    _particlePtr2indexMap.reserve(_aosNeighborLists.size());

    if (not _soaParticleOrder.empty()) {
      if (_soaParticleOrder.size() != _aosNeighborLists.size()) {
        utils::ExceptionHandler::exception(
            "VerletLists::generateSoAListFromAoSVerletLists(): sorted SoA particle order size ({}) does not match AoS "
            "neighbor-list size ({}).",
            _soaParticleOrder.size(), _aosNeighborLists.size());
      }

      for (size_t index = 0; index < _soaParticleOrder.size(); ++index) {
        // The explicit sorted order defines the SoA index of each particle.
        _particlePtr2indexMap[_soaParticleOrder[index]] = index;
      }

    } else {
      size_t index = 0;

      // Existing fallback path. Here we have to iterate over all particles, as particles might be later on marked for
      // deletion, and we cannot differentiate them from particles already marked for deletion.
      for (auto iter = this->begin(IteratorBehavior::ownedOrHaloOrDummy); iter.isValid(); ++iter, ++index) {
        // set the map
        _particlePtr2indexMap[&(*iter)] = index;
      }
    }
    size_t accumulatedListSize = 0;

    for (const auto &[particlePtr, neighborPtrVector] : _aosNeighborLists) {
      accumulatedListSize += neighborPtrVector.size();

      const auto centerIndexIter = _particlePtr2indexMap.find(particlePtr);
      if (centerIndexIter == _particlePtr2indexMap.end()) {
        utils::ExceptionHandler::exception(
            "VerletLists::generateSoAListFromAoSVerletLists(): center particle missing from particle-to-SoA-index "
            "map.");
      }

      const size_t i_id = centerIndexIter->second;
      // each soa neighbor list should be of the same size as for aos
      _soaNeighborLists[i_id].resize(neighborPtrVector.size());

      size_t j = 0;
      for (auto &neighborPtr : neighborPtrVector) {
        const auto neighborIndexIter = _particlePtr2indexMap.find(neighborPtr);
        if (neighborIndexIter == _particlePtr2indexMap.end()) {
          utils::ExceptionHandler::exception(
              "VerletLists::generateSoAListFromAoSVerletLists(): neighbor particle missing from particle-to-SoA-index "
              "map.");
        }

        _soaNeighborLists[i_id][j] = neighborIndexIter->second;
        j++;
      }
    }

    if (not _soaParticleOrder.empty()) {
      // The explicit SoA particle order makes neighboring indices spatially meaningful.
      // Sorting each neighbor vector by index keeps the interaction set unchanged, but
      // makes the neighbor access order more sequential in the SoA arrays.
      for (auto &neighborList : _soaNeighborLists) {
        std::sort(neighborList.begin(), neighborList.end());
      }
    }

    AutoPasLog(DEBUG,
               "VerletLists::generateSoAListFromAoSVerletLists: average verlet list "
               "size is {}",
               static_cast<double>(accumulatedListSize) / _aosNeighborLists.size());
    _soaListIsValid = true;
  }

 private:
  /**
   * Neighbor Lists: Map of particle pointers to vector of particle pointers.
   */
  typename VerletListHelpers<Particle_T>::NeighborListAoSType _aosNeighborLists;

  /**
   * Mapping of every particle, represented by its pointer, to an index.
   * The index indexes all particles in the container.
   */
  std::unordered_map<const Particle_T *, size_t> _particlePtr2indexMap;

  /**
   * Explicit particle order for sorted SoA traversal.
   *
   * If populated, _soaParticleOrder[i] is the particle stored at SoA index i.
   * For VerletListsReferences with global particle sorting enabled, this order
   * follows the sorted global ParticleVector.
   *
   * This vector is used consistently for SoA index mapping, SoA loading, and SoA
   * extraction. If it is empty, the traversal falls back to the existing
   * cell-based SoA order.
   */
  std::vector<Particle_T *> _soaParticleOrder;

  /**
   * verlet list for SoA:
   * For every Particle, identified via the _particlePtr2indexMap, a vector of its neighbor indices is stored.
   */
  std::vector<std::vector<size_t, AlignedAllocator<size_t>>> _soaNeighborLists;

  /**
   * Shows if the SoA neighbor list is currently valid.
   */
  bool _soaListIsValid{false};

  /**
   * Specifies for what data layout the verlet lists are build.
   */
  BuildVerletListType _buildVerletListType;
};

}  // namespace autopas
