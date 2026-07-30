/**
 * @file ParticleVector.h
 *
 * @author lunaticcoding
 * @date 04.05.2020
 */

#pragma once

#include <algorithm>
#include <vector>

#include "autopas/utils/WrapOpenMP.h"

/**
 * ParticleVector class.
 * This class uses a std::vector to store particles and allows access to its references.
 * It also keeps track, which references are no longer valid, which happens
 * when operations like delete and resize are performed.
 * @tparam Particle_T of the Particle that is being stored
 */
template <class Particle_T>
class ParticleVector {
 public:
  ParticleVector() = default;

  /**
   * Returns the dirty flag, indicating whether Particles exist in the vector that are not stored in a cell yet.
   * @return True if dirty, false otherwise
   */
  bool isDirty() { return _dirty; }

  /**
   * Marks the ParticleVector as clean. Should be called after updating the references of dirty particles.
   */
  void markAsClean() {
    _dirty = false;
    _dirtyIndex = _particleListImp.size();
  }

  /**
   * Remove all particles from the container and mark it as dirty.
   */
  void clearAllParticles() {
    _particleListImp.clear();
    _dirty = true;
    _dirtyIndex = 0;
  }

  /**
   * Remove all halo particles from the container and mark it as dirty.
   */
  void clearHaloParticles() {
    _particleListImp.erase(std::remove_if(_particleListImp.begin(), _particleListImp.end(),
                                          [](const auto &particle) { return particle.isHalo(); }),
                           _particleListImp.end());
    _dirty = true;
    _dirtyIndex = 0;
  }

  /**
   * Remove all dummy particles from the container and mark it as dirty.
   */
  void deleteDummyParticles() {
    _particleListImp.erase(std::remove_if(_particleListImp.begin(), _particleListImp.end(),
                                          [](const auto &particle) { return particle.isDummy(); }),
                           _particleListImp.end());
    _dirty = true;
    _dirtyIndex = 0;
  }

  /**
   * Add a Particle to the data structure.
   * @param particle A reference to the particle to be stored
   */
  void push_back(const Particle_T &particle) {
    _particleListLock.lock();
    _dirty = true;
    if (_particleListImp.capacity() == _particleListImp.size()) {
      _dirtyIndex = 0;
    }
    _particleListImp.push_back(particle);
    _particleListLock.unlock();
  }

  /**
   * Sort all particles in the underlying storage and mark all cell references as dirty.
   *
   * Sorting physically reorders the Particle_T objects inside the global particle vector.
   * Since ReferenceParticleCell stores Particle_T pointers into this vector, all existing
   * cell references must be considered invalid after this operation.
   *
   * Setting _dirtyIndex to 0 forces LinkedCellsReferences::updateDirtyParticleReferences()
   * to clear and rebuild all cell reference lists.
   *
   * @tparam Compare Comparator type.
   * @param compare Comparator for Particle_T objects.
   */
  template <class Compare>
  void sortParticles(Compare compare) {
    std::sort(_particleListImp.begin(), _particleListImp.end(), compare);

    // Sorting can move particles to different addresses, so every existing pointer
    // stored in ReferenceParticleCell has to be rebuilt.
    _dirty = true;
    _dirtyIndex = 0;
  }

  /**
   * Get the number of Particles in the data structure.
   * @return Total number of Particles
   */
  int totalSize() { return _particleListImp.size(); }

  /**
   * Get the number of dirty Particles in the data structure.
   * @return Number of dirty Particles
   */
  int dirtySize() { return totalSize() - _dirtyIndex; }

  /**
   * Indicates, whether References already stored in cells need to be updated.
   * @return Boolean indicating the above
   */
  bool needsRebuild() { return _dirtyIndex == 0; }

  /**
   * Begin of the iterator over dirty Particles
   * @return Start of the iterator
   */
  auto beginDirty() { return _particleListImp.begin() + _dirtyIndex; }
  /**
   * End of the iterator over dirty Particles
   * @return End of the iterator
   */
  auto endDirty() { return _particleListImp.end(); }

  /**
   * Iterate over all particles and execute lambda function on them.
   * @param forEachLambda lambda function that defines how to modify particles
   */
  template <typename Lambda>
  void forEach(Lambda forEachLambda) {
    for (Particle_T &p : _particleListImp) {
      forEachLambda(p);
    }
  }

  /**
   * Iterate over all particles in their physical storage order.
   *
   * This is intentionally equivalent to forEach(), but the explicit name is useful
   * for code paths where the order itself matters, e.g. constructing a SoA buffer
   * from a globally sorted ParticleVector.
   *
   * @tparam Lambda Callable type accepting Particle_T&.
   * @param forEachLambda Function executed for every particle.
   */
  template <typename Lambda>
  void forEachInStorageOrder(Lambda forEachLambda) {
    forEach(forEachLambda);
  }

  /**
   * Iterate over all particles and execute lambda function on them.
   * @param reduceLambda lambda function that defines how to modify particles
   * @param result reference to variable where result will be stored after operation
   */
  template <typename Lambda, typename A>
  void reduce(Lambda reduceLambda, A &result) {
    for (Particle_T &p : _particleListImp) {
      reduceLambda(p, result);
    }
  }

 private:
  /**
   * Flag indicating whether there are out-of-date references in the vector.
   */
  bool _dirty = false;
  /**
   * Index of the first out-of-date reference.
   */
  size_t _dirtyIndex{0};
  autopas::AutoPasLock _particleListLock;
  std::vector<Particle_T> _particleListImp;
};
