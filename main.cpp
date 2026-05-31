#include <GLFW/glfw3.h>

#include <assimp/Importer.hpp>
#include <assimp/matrix4x4.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/quaternion.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include <zlib.h>

namespace {
constexpr int WindowWidth = 1280;
constexpr int WindowHeight = 720;
constexpr float CharacterMoveSpeed = 3.2F;
constexpr float CharacterAnimationPlaybackSpeed = 0.85F;
constexpr float CharacterTransitionAnimationPlaybackSpeed = 1.35F;
constexpr float ZoomSpeed = 1.25F;
constexpr float MinCameraDistance = 4.0F;
constexpr float MaxCameraDistance = 40.0F;
constexpr float FieldOfView = 45.0F;
constexpr float NearPlane = 0.1F;
constexpr float FarPlane = 200.0F;
constexpr int MaxVertexBones = 4;
constexpr const char *BodyModelPath = "media/models/Bob.fbx";
constexpr const char *IdleAnimationPath = "media/anim_x/bob/Bob_Idle.fbx";
constexpr const char *IdleToWalkAnimationPath =
    "media/animations/Bob_IdleToWalk.fbx";
constexpr const char *WalkToStopAnimationPath =
    "media/animations/Bob_WalkToStop.fbx";
constexpr const char *WalkAnimationPath = "media/anim_x/bob/Bob_Walk.fbx";
constexpr const char *BodyTexturePath = "media/textures/Body MaleBody01.png";

struct Vertex {
  glm::vec3 position{};
  glm::vec3 staticPosition{};
  glm::vec3 normal{0.0F, 1.0F, 0.0F};
  glm::vec3 staticNormal{0.0F, 1.0F, 0.0F};
  glm::vec2 texCoord{0.0F, 0.0F};
  std::array<int, MaxVertexBones> boneIds{-1, -1, -1, -1};
  std::array<float, MaxVertexBones> boneWeights{0.0F, 0.0F, 0.0F, 0.0F};
};

struct Mesh {
  std::vector<Vertex> vertices;
  std::vector<unsigned int> indices;
  bool isSkinned = false;
};

struct Bone {
  std::string name;
  glm::mat4 offsetMatrix{1.0F};
};

struct Texture2D {
  GLuint id = 0;
  int width = 0;
  int height = 0;

  [[nodiscard]] bool isLoaded() const { return id != 0; }
};

struct PngImage {
  int width = 0;
  int height = 0;
  std::vector<unsigned char> pixels;

  [[nodiscard]] bool isLoaded() const { return !pixels.empty(); }
};

struct SkeletonNode {
  std::string name;
  glm::mat4 transform{1.0F};
  std::vector<SkeletonNode> children;
};

struct Model {
  std::vector<Mesh> meshes;
  std::vector<Bone> bones;
  std::unordered_map<std::string, int> boneIndexByName;
  SkeletonNode rootNode;
  glm::mat4 globalInverseTransform{1.0F};
  unsigned int animationCount = 0;

  [[nodiscard]] bool isLoaded() const { return !meshes.empty(); }

  [[nodiscard]] bool hasSkeleton() const { return !bones.empty(); }
};

struct VectorKey {
  double time = 0.0;
  glm::vec3 value{};
};

struct QuaternionKey {
  double time = 0.0;
  glm::quat value{1.0F, 0.0F, 0.0F, 0.0F};
};

struct AnimationChannel {
  std::string nodeName;
  std::vector<VectorKey> positions;
  std::vector<QuaternionKey> rotations;
  std::vector<VectorKey> scales;
};

struct AnimationClip {
  std::string name;
  double durationTicks = 0.0;
  double ticksPerSecond = 24.0;
  bool retargetFirstFrameToBindPose = false;
  bool keepBindPoseTranslations = false;
  std::vector<AnimationChannel> channels;
  std::unordered_map<std::string, std::size_t> channelIndexByNodeName;

  [[nodiscard]] bool isLoaded() const {
    return !channels.empty() && durationTicks > 0.0;
  }
};

struct Camera {
  glm::vec3 target{0.0F, 0.0F, 0.0F};
  float distance = 14.0F;

  [[nodiscard]] glm::vec3 position() const {
    const glm::vec3 isometricOffset{1.0F, 1.25F, 1.0F};
    return target + glm::normalize(isometricOffset) * distance;
  }

  [[nodiscard]] glm::vec3 forward() const {
    return glm::normalize(target - position());
  }

  [[nodiscard]] glm::vec3 right() const {
    return glm::normalize(glm::cross(forward(), glm::vec3{0.0F, 1.0F, 0.0F}));
  }

  [[nodiscard]] glm::mat4 viewMatrix() const {
    return glm::lookAt(position(), target, glm::vec3{0.0F, 1.0F, 0.0F});
  }

  void zoom(float amount) {
    distance = std::clamp(distance - amount * ZoomSpeed, MinCameraDistance,
                          MaxCameraDistance);
  }
};

enum class CharacterAnimationState {
  Idle,
  IdleToWalk,
  Walk,
  WalkToStop,
};

struct Character {
  glm::vec3 position{0.0F, 0.0F, 0.0F};
  glm::vec3 facing{0.0F, 0.0F, 1.0F};
  float animationTime = 0.0F;
  bool isMoving = false;
  CharacterAnimationState animationState = CharacterAnimationState::Idle;
};

struct InputState {
  Camera camera;
  Character character;
};

glm::mat4 toGlm(const aiMatrix4x4 &matrix) {
  glm::mat4 result{1.0F};
  result[0][0] = matrix.a1;
  result[1][0] = matrix.a2;
  result[2][0] = matrix.a3;
  result[3][0] = matrix.a4;
  result[0][1] = matrix.b1;
  result[1][1] = matrix.b2;
  result[2][1] = matrix.b3;
  result[3][1] = matrix.b4;
  result[0][2] = matrix.c1;
  result[1][2] = matrix.c2;
  result[2][2] = matrix.c3;
  result[3][2] = matrix.c4;
  result[0][3] = matrix.d1;
  result[1][3] = matrix.d2;
  result[2][3] = matrix.d3;
  result[3][3] = matrix.d4;
  return result;
}

glm::vec3 toGlm(const aiVector3D &vector) {
  return {vector.x, vector.y, vector.z};
}

glm::quat toGlm(const aiQuaternion &quaternion) {
  return {quaternion.w, quaternion.x, quaternion.y, quaternion.z};
}

std::string normalizeAssimpName(std::string name) {
  const std::size_t separatorPosition = name.find_last_of("|:/\\");
  if (separatorPosition != std::string::npos &&
      separatorPosition + 1 < name.size()) {
    name = name.substr(separatorPosition + 1);
  }

  const std::size_t dotPosition = name.find_last_of('.');
  if (dotPosition == std::string::npos || dotPosition + 1 >= name.size()) {
    return name;
  }

  const bool suffixIsNumeric = std::all_of(
      name.begin() + static_cast<std::ptrdiff_t>(dotPosition + 1), name.end(),
      [](char value) { return value >= '0' && value <= '9'; });
  if (suffixIsNumeric) {
    name.erase(dotPosition);
  }
  return name;
}

std::string normalizedAnimationSearchName(const std::string &name) {
  std::string normalized;
  normalized.reserve(name.size());
  for (char value : name) {
    if (value != '_' && value != '-' && value != ' ' && value != '|') {
      normalized.push_back(
          static_cast<char>(std::tolower(static_cast<unsigned char>(value))));
    }
  }
  return normalized;
}

const aiAnimation &chooseAnimation(const aiScene &scene,
                                   const std::string &preferredName) {
  const std::string preferred = normalizedAnimationSearchName(preferredName);
  const aiAnimation *bestAnimation = scene.mAnimations[0];
  int bestScore = -1;

  for (unsigned int animationIndex = 0; animationIndex < scene.mNumAnimations;
       ++animationIndex) {
    const aiAnimation &animation = *scene.mAnimations[animationIndex];
    const std::string candidate =
        normalizedAnimationSearchName(animation.mName.C_Str());
    int score = 0;
    if (!preferred.empty() && candidate.find(preferred) != std::string::npos) {
      score += 100;
    }
    if (animation.mNumChannels > bestAnimation->mNumChannels) {
      score += 10;
    }
    if (animation.mDuration > bestAnimation->mDuration) {
      score += 1;
    }

    if (score > bestScore) {
      bestScore = score;
      bestAnimation = &animation;
    }
  }

  return *bestAnimation;
}

SkeletonNode buildSkeletonNode(const aiNode &node) {
  SkeletonNode result;
  result.name = normalizeAssimpName(node.mName.C_Str());
  result.transform = toGlm(node.mTransformation);
  result.children.reserve(node.mNumChildren);
  for (unsigned int childIndex = 0; childIndex < node.mNumChildren;
       ++childIndex) {
    result.children.push_back(buildSkeletonNode(*node.mChildren[childIndex]));
  }
  return result;
}

int findOrCreateBone(Model &model, const aiBone &assimpBone) {
  const std::string boneName = normalizeAssimpName(assimpBone.mName.C_Str());
  const auto existing = model.boneIndexByName.find(boneName);
  if (existing != model.boneIndexByName.end()) {
    return existing->second;
  }

  const int boneIndex = static_cast<int>(model.bones.size());
  model.boneIndexByName.emplace(boneName, boneIndex);
  model.bones.push_back(Bone{boneName, toGlm(assimpBone.mOffsetMatrix)});
  return boneIndex;
}

void addBoneWeight(Vertex &vertex, int boneId, float weight) {
  for (int slot = 0; slot < MaxVertexBones; ++slot) {
    if (vertex.boneIds[slot] < 0) {
      vertex.boneIds[slot] = boneId;
      vertex.boneWeights[slot] = weight;
      return;
    }
  }

  auto smallestWeight =
      std::min_element(vertex.boneWeights.begin(), vertex.boneWeights.end());
  if (smallestWeight != vertex.boneWeights.end() && weight > *smallestWeight) {
    const int slot = static_cast<int>(
        std::distance(vertex.boneWeights.begin(), smallestWeight));
    vertex.boneIds[slot] = boneId;
    vertex.boneWeights[slot] = weight;
  }
}

void normalizeBoneWeights(Vertex &vertex) {
  float totalWeight = 0.0F;
  for (float weight : vertex.boneWeights) {
    totalWeight += weight;
  }

  if (totalWeight <= std::numeric_limits<float>::epsilon()) {
    return;
  }

  for (float &weight : vertex.boneWeights) {
    weight /= totalWeight;
  }
}

void appendMesh(const aiMesh &assimpMesh, const glm::mat4 &transform,
                Model &model) {
  Mesh mesh;
  mesh.vertices.reserve(assimpMesh.mNumVertices);

  const glm::mat3 normalMatrix =
      glm::transpose(glm::inverse(glm::mat3(transform)));
  for (unsigned int vertexIndex = 0; vertexIndex < assimpMesh.mNumVertices;
       ++vertexIndex) {
    const glm::vec3 sourcePosition = toGlm(assimpMesh.mVertices[vertexIndex]);
    const glm::vec4 transformedPosition =
        transform * glm::vec4{sourcePosition, 1.0F};

    glm::vec3 normal{0.0F, 1.0F, 0.0F};
    glm::vec3 staticNormal{0.0F, 1.0F, 0.0F};
    if (assimpMesh.HasNormals()) {
      normal = glm::normalize(toGlm(assimpMesh.mNormals[vertexIndex]));
      staticNormal = glm::normalize(normalMatrix * normal);
    }

    glm::vec2 texCoord{0.0F, 0.0F};
    if (assimpMesh.HasTextureCoords(0)) {
      const aiVector3D &sourceTexCoord =
          assimpMesh.mTextureCoords[0][vertexIndex];
      texCoord = {sourceTexCoord.x, sourceTexCoord.y};
    }

    mesh.vertices.push_back(Vertex{sourcePosition,
                                   glm::vec3{transformedPosition}, normal,
                                   staticNormal, texCoord});
  }

  for (unsigned int boneIndex = 0; boneIndex < assimpMesh.mNumBones;
       ++boneIndex) {
    const aiBone &assimpBone = *assimpMesh.mBones[boneIndex];
    const int engineBoneId = findOrCreateBone(model, assimpBone);
    for (unsigned int weightIndex = 0; weightIndex < assimpBone.mNumWeights;
         ++weightIndex) {
      const aiVertexWeight &weight = assimpBone.mWeights[weightIndex];
      if (weight.mVertexId < mesh.vertices.size()) {
        addBoneWeight(mesh.vertices[weight.mVertexId], engineBoneId,
                      weight.mWeight);
      }
    }
  }

  for (Vertex &vertex : mesh.vertices) {
    normalizeBoneWeights(vertex);
  }

  for (unsigned int faceIndex = 0; faceIndex < assimpMesh.mNumFaces;
       ++faceIndex) {
    const aiFace &face = assimpMesh.mFaces[faceIndex];
    if (face.mNumIndices != 3) {
      continue;
    }

    mesh.indices.push_back(face.mIndices[0]);
    mesh.indices.push_back(face.mIndices[1]);
    mesh.indices.push_back(face.mIndices[2]);
  }

  mesh.isSkinned = assimpMesh.mNumBones > 0;
  if (!mesh.vertices.empty() && !mesh.indices.empty()) {
    model.meshes.push_back(std::move(mesh));
  }
}

void appendNodeMeshes(const aiScene &scene, const aiNode &node,
                      const glm::mat4 &parentTransform, Model &model) {
  const glm::mat4 transform = parentTransform * toGlm(node.mTransformation);

  for (unsigned int meshIndex = 0; meshIndex < node.mNumMeshes; ++meshIndex) {
    const unsigned int sceneMeshIndex = node.mMeshes[meshIndex];
    if (sceneMeshIndex < scene.mNumMeshes) {
      appendMesh(*scene.mMeshes[sceneMeshIndex], transform, model);
    }
  }

  for (unsigned int childIndex = 0; childIndex < node.mNumChildren;
       ++childIndex) {
    appendNodeMeshes(scene, *node.mChildren[childIndex], transform, model);
  }
}

Model loadModel(const std::filesystem::path &path) {
  Model model;
  if (!std::filesystem::exists(path)) {
    std::cerr << "Model file was not found: " << path << "\n";
    return model;
  }

  Assimp::Importer importer;
  const aiScene *scene = importer.ReadFile(
      path.string(), aiProcess_Triangulate | aiProcess_JoinIdenticalVertices |
                         aiProcess_GenSmoothNormals |
                         aiProcess_LimitBoneWeights |
                         aiProcess_ImproveCacheLocality);

  if (scene == nullptr || scene->mRootNode == nullptr) {
    std::cerr << "Failed to load model " << path << ": "
              << importer.GetErrorString() << "\n";
    return model;
  }

  model.rootNode = buildSkeletonNode(*scene->mRootNode);
  model.globalInverseTransform =
      glm::inverse(toGlm(scene->mRootNode->mTransformation));
  model.animationCount = scene->mNumAnimations;
  appendNodeMeshes(*scene, *scene->mRootNode, glm::mat4{1.0F}, model);

  std::cout << "Loaded " << path << " with " << model.meshes.size()
            << " mesh(es), " << model.bones.size() << " bone(s), and "
            << model.animationCount << " embedded animation(s).\n";
  return model;
}

AnimationClip loadAnimationClip(const std::filesystem::path &path,
                                std::string fallbackName,
                                bool retargetFirstFrameToBindPose = false,
                                bool keepBindPoseTranslations = false) {
  AnimationClip clip;
  clip.retargetFirstFrameToBindPose = retargetFirstFrameToBindPose;
  clip.keepBindPoseTranslations = keepBindPoseTranslations;
  if (!std::filesystem::exists(path)) {
    std::cerr << "Animation file was not found: " << path << "\n";
    return clip;
  }

  Assimp::Importer importer;
  const aiScene *scene = importer.ReadFile(path.string(), 0);
  if (scene == nullptr || scene->mNumAnimations == 0) {
    std::cerr << "Failed to load animation " << path << ": "
              << importer.GetErrorString() << "\n";
    return clip;
  }

  const aiAnimation &animation = chooseAnimation(*scene, fallbackName);
  clip.name = animation.mName.C_Str();
  if (clip.name.empty()) {
    clip.name = std::move(fallbackName);
  }

  clip.durationTicks = animation.mDuration;
  clip.ticksPerSecond =
      animation.mTicksPerSecond > 0.0 ? animation.mTicksPerSecond : 24.0;
  clip.channels.reserve(animation.mNumChannels);

  for (unsigned int channelIndex = 0; channelIndex < animation.mNumChannels;
       ++channelIndex) {
    const aiNodeAnim &assimpChannel = *animation.mChannels[channelIndex];
    AnimationChannel channel;
    channel.nodeName = normalizeAssimpName(assimpChannel.mNodeName.C_Str());

    channel.positions.reserve(assimpChannel.mNumPositionKeys);
    for (unsigned int keyIndex = 0; keyIndex < assimpChannel.mNumPositionKeys;
         ++keyIndex) {
      const aiVectorKey &key = assimpChannel.mPositionKeys[keyIndex];
      channel.positions.push_back(VectorKey{key.mTime, toGlm(key.mValue)});
    }

    channel.rotations.reserve(assimpChannel.mNumRotationKeys);
    for (unsigned int keyIndex = 0; keyIndex < assimpChannel.mNumRotationKeys;
         ++keyIndex) {
      const aiQuatKey &key = assimpChannel.mRotationKeys[keyIndex];
      channel.rotations.push_back(QuaternionKey{key.mTime, toGlm(key.mValue)});
    }

    channel.scales.reserve(assimpChannel.mNumScalingKeys);
    for (unsigned int keyIndex = 0; keyIndex < assimpChannel.mNumScalingKeys;
         ++keyIndex) {
      const aiVectorKey &key = assimpChannel.mScalingKeys[keyIndex];
      channel.scales.push_back(VectorKey{key.mTime, toGlm(key.mValue)});
    }

    clip.channelIndexByNodeName[channel.nodeName] = clip.channels.size();
    clip.channels.push_back(std::move(channel));
  }

  std::cout << "Loaded animation " << path << " as '" << clip.name << "' with "
            << clip.channels.size() << " channel(s), " << clip.durationTicks
            << " tick(s), " << clip.ticksPerSecond << " tick(s)/second.\n";
  return clip;
}

float animationDurationSeconds(const AnimationClip &animation) {
  if (!animation.isLoaded() || animation.ticksPerSecond <= 0.0) {
    return 0.0F;
  }

  return static_cast<float>(animation.durationTicks / animation.ticksPerSecond);
}

std::size_t countMatchingAnimationChannels(const Model &model,
                                           const AnimationClip &animation) {
  std::size_t matchingChannels = 0;
  for (const AnimationChannel &channel : animation.channels) {
    if (model.boneIndexByName.contains(channel.nodeName)) {
      ++matchingChannels;
    }
  }
  return matchingChannels;
}

void printAnimationMatchReport(const Model &model,
                               const AnimationClip &animation) {
  if (!animation.isLoaded()) {
    return;
  }

  const std::size_t matchingChannels =
      countMatchingAnimationChannels(model, animation);
  std::cout << "Animation '" << animation.name << "' matches "
            << matchingChannels << "/" << animation.channels.size()
            << " channel(s) to " << model.bones.size() << " model bone(s).\n";
  if (matchingChannels == 0) {
    std::cerr << "No animation channels matched model bones. Check that the "
                 "FBX action uses the same Bip01 bone names as Bob.fbx.\n";
  }
}

std::vector<unsigned char> readBinaryFile(const std::filesystem::path &path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) {
    return {};
  }

  return {std::istreambuf_iterator<char>{file},
          std::istreambuf_iterator<char>{}};
}

std::uint32_t readBigEndianU32(const std::vector<unsigned char> &bytes,
                               std::size_t offset) {
  return (static_cast<std::uint32_t>(bytes[offset]) << 24U) |
         (static_cast<std::uint32_t>(bytes[offset + 1]) << 16U) |
         (static_cast<std::uint32_t>(bytes[offset + 2]) << 8U) |
         static_cast<std::uint32_t>(bytes[offset + 3]);
}

unsigned char paethPredictor(unsigned char left, unsigned char up,
                             unsigned char upperLeft) {
  const int predictor = static_cast<int>(left) + static_cast<int>(up) -
                        static_cast<int>(upperLeft);
  const int leftDistance = std::abs(predictor - static_cast<int>(left));
  const int upDistance = std::abs(predictor - static_cast<int>(up));
  const int upperLeftDistance =
      std::abs(predictor - static_cast<int>(upperLeft));

  if (leftDistance <= upDistance && leftDistance <= upperLeftDistance) {
    return left;
  }
  if (upDistance <= upperLeftDistance) {
    return up;
  }
  return upperLeft;
}

PngImage loadPngImage(const std::filesystem::path &path) {
  constexpr std::array<unsigned char, 8> PngSignature{137, 80, 78, 71,
                                                      13,  10, 26, 10};
  PngImage image;
  const std::vector<unsigned char> fileBytes = readBinaryFile(path);
  if (fileBytes.size() < PngSignature.size() ||
      !std::equal(PngSignature.begin(), PngSignature.end(),
                  fileBytes.begin())) {
    std::cerr << "Texture is not a PNG file: " << path << "\n";
    return image;
  }

  int sourceChannels = 0;
  std::vector<unsigned char> compressedPixels;
  std::size_t offset = PngSignature.size();
  while (offset + 12 <= fileBytes.size()) {
    const std::uint32_t chunkLength = readBigEndianU32(fileBytes, offset);
    offset += 4;
    const std::string chunkType{
        fileBytes.begin() + static_cast<std::ptrdiff_t>(offset),
        fileBytes.begin() + static_cast<std::ptrdiff_t>(offset + 4)};
    offset += 4;

    if (offset + chunkLength + 4 > fileBytes.size()) {
      std::cerr << "PNG chunk is truncated in texture: " << path << "\n";
      return {};
    }

    if (chunkType == "IHDR") {
      image.width = static_cast<int>(readBigEndianU32(fileBytes, offset));
      image.height = static_cast<int>(readBigEndianU32(fileBytes, offset + 4));
      const unsigned char bitDepth = fileBytes[offset + 8];
      const unsigned char colorType = fileBytes[offset + 9];
      const unsigned char compression = fileBytes[offset + 10];
      const unsigned char filter = fileBytes[offset + 11];
      const unsigned char interlace = fileBytes[offset + 12];

      if (bitDepth != 8 || compression != 0 || filter != 0 || interlace != 0 ||
          (colorType != 2 && colorType != 6)) {
        std::cerr << "Unsupported PNG texture format: " << path
                  << " (expected non-interlaced 8-bit RGB/RGBA).\n";
        return {};
      }
      sourceChannels = colorType == 6 ? 4 : 3;
    } else if (chunkType == "IDAT") {
      compressedPixels.insert(
          compressedPixels.end(),
          fileBytes.begin() + static_cast<std::ptrdiff_t>(offset),
          fileBytes.begin() +
              static_cast<std::ptrdiff_t>(offset + chunkLength));
    } else if (chunkType == "IEND") {
      break;
    }

    offset += chunkLength + 4;
  }

  if (image.width <= 0 || image.height <= 0 || sourceChannels == 0 ||
      compressedPixels.empty()) {
    std::cerr << "PNG texture is missing image data: " << path << "\n";
    return {};
  }

  const std::size_t rowBytes =
      static_cast<std::size_t>(image.width) * sourceChannels;
  std::vector<unsigned char> filteredPixels(
      (rowBytes + 1) * static_cast<std::size_t>(image.height));
  uLongf filteredSize = static_cast<uLongf>(filteredPixels.size());
  const int zlibResult =
      uncompress(filteredPixels.data(), &filteredSize, compressedPixels.data(),
                 static_cast<uLong>(compressedPixels.size()));
  if (zlibResult != Z_OK || filteredSize != filteredPixels.size()) {
    std::cerr << "Failed to decompress PNG texture: " << path << "\n";
    return {};
  }

  std::vector<unsigned char> sourcePixels(
      rowBytes * static_cast<std::size_t>(image.height));
  for (int y = 0; y < image.height; ++y) {
    const std::size_t filteredRowOffset =
        static_cast<std::size_t>(y) * (rowBytes + 1);
    const unsigned char filterType = filteredPixels[filteredRowOffset];
    const unsigned char *filteredRow =
        filteredPixels.data() + filteredRowOffset + 1;
    unsigned char *decodedRow =
        sourcePixels.data() + static_cast<std::size_t>(y) * rowBytes;
    const unsigned char *previousRow =
        y > 0 ? sourcePixels.data() + static_cast<std::size_t>(y - 1) * rowBytes
              : nullptr;

    for (std::size_t x = 0; x < rowBytes; ++x) {
      const unsigned char raw = filteredRow[x];
      const unsigned char left = x >= static_cast<std::size_t>(sourceChannels)
                                     ? decodedRow[x - sourceChannels]
                                     : 0;
      const unsigned char up = previousRow != nullptr ? previousRow[x] : 0;
      const unsigned char upperLeft =
          previousRow != nullptr &&
                  x >= static_cast<std::size_t>(sourceChannels)
              ? previousRow[x - sourceChannels]
              : 0;

      switch (filterType) {
      case 0:
        decodedRow[x] = raw;
        break;
      case 1:
        decodedRow[x] = static_cast<unsigned char>(raw + left);
        break;
      case 2:
        decodedRow[x] = static_cast<unsigned char>(raw + up);
        break;
      case 3:
        decodedRow[x] = static_cast<unsigned char>(
            raw + ((static_cast<int>(left) + static_cast<int>(up)) / 2));
        break;
      case 4:
        decodedRow[x] = static_cast<unsigned char>(
            raw + paethPredictor(left, up, upperLeft));
        break;
      default:
        std::cerr << "Unsupported PNG filter in texture: " << path << "\n";
        return {};
      }
    }
  }

  image.pixels.resize(static_cast<std::size_t>(image.width) * image.height * 4);
  for (int y = 0; y < image.height; ++y) {
    const int flippedY = image.height - 1 - y;
    for (int x = 0; x < image.width; ++x) {
      const std::size_t sourceOffset =
          (static_cast<std::size_t>(y) * image.width + x) * sourceChannels;
      const std::size_t targetOffset =
          (static_cast<std::size_t>(flippedY) * image.width + x) * 4;
      image.pixels[targetOffset] = sourcePixels[sourceOffset];
      image.pixels[targetOffset + 1] = sourcePixels[sourceOffset + 1];
      image.pixels[targetOffset + 2] = sourcePixels[sourceOffset + 2];
      image.pixels[targetOffset + 3] =
          sourceChannels == 4 ? sourcePixels[sourceOffset + 3] : 255;
    }
  }
  return image;
}

Texture2D loadTexture2D(const std::filesystem::path &path) {
  Texture2D texture;
  if (!std::filesystem::exists(path)) {
    std::cerr << "Texture file was not found: " << path << "\n";
    return texture;
  }

  const PngImage image = loadPngImage(path);
  if (!image.isLoaded()) {
    return texture;
  }

  glGenTextures(1, &texture.id);
  glBindTexture(GL_TEXTURE_2D, texture.id);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
  glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
  glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0, GL_RGBA,
               GL_UNSIGNED_BYTE, image.pixels.data());
  glBindTexture(GL_TEXTURE_2D, 0);

  texture.width = image.width;
  texture.height = image.height;
  std::cout << "Loaded texture " << path << " (" << texture.width << "x"
            << texture.height << ").\n";
  return texture;
}

void errorCallback(int error, const char *description) {
  std::cerr << "GLFW error " << error << ": " << description << '\n';
}

void framebufferSizeCallback(GLFWwindow *, int width, int height) {
  glViewport(0, 0, width, height);
}

void scrollCallback(GLFWwindow *window, double, double yOffset) {
  auto *input = static_cast<InputState *>(glfwGetWindowUserPointer(window));
  if (input == nullptr) {
    return;
  }

  input->camera.zoom(static_cast<float>(yOffset));
}

glm::vec3 screenDirectionToWorldDirection(float screenRight, float screenUp) {
  const glm::vec3 worldScreenRight =
      glm::normalize(glm::vec3{1.0F, 0.0F, -1.0F});
  const glm::vec3 worldScreenUp = glm::normalize(glm::vec3{-1.0F, 0.0F, -1.0F});
  return worldScreenRight * screenRight + worldScreenUp * screenUp;
}

void updateCharacterAnimationState(Character &character, bool wantsToMove,
                                   float deltaTime,
                                   const AnimationClip &idleToWalkAnimation,
                                   const AnimationClip &walkToStopAnimation) {
  if (!wantsToMove) {
    character.isMoving = false;
    if (character.animationState == CharacterAnimationState::Idle) {
      character.animationTime += deltaTime;
      return;
    }

    if (character.animationState != CharacterAnimationState::WalkToStop) {
      character.animationState = CharacterAnimationState::WalkToStop;
      character.animationTime = 0.0F;
    }

    const float transitionDuration =
        animationDurationSeconds(walkToStopAnimation);
    if (transitionDuration <= std::numeric_limits<float>::epsilon()) {
      character.animationState = CharacterAnimationState::Idle;
      character.animationTime = 0.0F;
      return;
    }

    character.animationTime += deltaTime;
    if (character.animationTime >= transitionDuration) {
      character.animationState = CharacterAnimationState::Idle;
      character.animationTime = 0.0F;
    }
    return;
  }

  const bool startedMoving = !character.isMoving;
  character.isMoving = true;
  if (startedMoving ||
      character.animationState == CharacterAnimationState::Idle ||
      character.animationState == CharacterAnimationState::WalkToStop) {
    character.animationState = CharacterAnimationState::IdleToWalk;
    character.animationTime = 0.0F;
  }

  if (character.animationState == CharacterAnimationState::IdleToWalk) {
    const float transitionDuration =
        animationDurationSeconds(idleToWalkAnimation);
    if (transitionDuration <= std::numeric_limits<float>::epsilon()) {
      character.animationState = CharacterAnimationState::Walk;
      character.animationTime = 0.0F;
      return;
    }

    character.animationTime += deltaTime;
    if (character.animationTime >= transitionDuration) {
      character.animationState = CharacterAnimationState::Walk;
      character.animationTime =
          std::fmod(character.animationTime, transitionDuration);
    }
    return;
  }

  character.animationTime += deltaTime;
}

void processKeyboard(GLFWwindow *window, InputState &input, float deltaTime,
                     const AnimationClip &idleToWalkAnimation,
                     const AnimationClip &walkToStopAnimation) {
  if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) {
    glfwSetWindowShouldClose(window, GLFW_TRUE);
  }

  glm::vec3 movement{0.0F, 0.0F, 0.0F};
  if (glfwGetKey(window, GLFW_KEY_W) == GLFW_PRESS) {
    movement += screenDirectionToWorldDirection(0.0F, 1.0F);
  }
  if (glfwGetKey(window, GLFW_KEY_S) == GLFW_PRESS) {
    movement += screenDirectionToWorldDirection(0.0F, -1.0F);
  }
  if (glfwGetKey(window, GLFW_KEY_D) == GLFW_PRESS) {
    movement += screenDirectionToWorldDirection(1.0F, 0.0F);
  }
  if (glfwGetKey(window, GLFW_KEY_A) == GLFW_PRESS) {
    movement += screenDirectionToWorldDirection(-1.0F, 0.0F);
  }

  const bool wantsToMove = glm::length(movement) > 0.0F;
  if (wantsToMove) {
    const glm::vec3 direction = glm::normalize(movement);
    input.character.position += direction * CharacterMoveSpeed * deltaTime;
    input.character.facing = direction;
  }

  const bool isTransitioning =
      (wantsToMove &&
       input.character.animationState != CharacterAnimationState::Walk) ||
      (!wantsToMove &&
       input.character.animationState != CharacterAnimationState::Idle);
  const float animationPlaybackSpeed =
      isTransitioning ? CharacterTransitionAnimationPlaybackSpeed
                      : CharacterAnimationPlaybackSpeed;
  updateCharacterAnimationState(input.character, wantsToMove,
                                deltaTime * animationPlaybackSpeed,
                                idleToWalkAnimation, walkToStopAnimation);
  input.camera.target = input.character.position;
}

void loadMatrix(GLenum matrixMode, const glm::mat4 &matrix) {
  glMatrixMode(matrixMode);
  glLoadMatrixf(glm::value_ptr(matrix));
}

void drawGroundGrid() {
  constexpr int GridHalfSize = 20;
  glColor3f(0.28F, 0.42F, 0.24F);
  glBegin(GL_LINES);
  for (int line = -GridHalfSize; line <= GridHalfSize; ++line) {
    glVertex3f(static_cast<float>(line), 0.0F,
               static_cast<float>(-GridHalfSize));
    glVertex3f(static_cast<float>(line), 0.0F,
               static_cast<float>(GridHalfSize));
    glVertex3f(static_cast<float>(-GridHalfSize), 0.0F,
               static_cast<float>(line));
    glVertex3f(static_cast<float>(GridHalfSize), 0.0F,
               static_cast<float>(line));
  }
  glEnd();
}

void drawCube() {
  struct Face {
    std::array<glm::vec3, 4> vertices;
    glm::vec3 color;
  };

  constexpr float Bottom = 0.0F;
  constexpr float Top = 1.5F;
  constexpr float Left = -0.75F;
  constexpr float Right = 0.75F;
  constexpr float Back = -0.75F;
  constexpr float Front = 0.75F;

  const std::array<Face, 6> faces{{
      {{{{Left, Bottom, Front},
         {Right, Bottom, Front},
         {Right, Top, Front},
         {Left, Top, Front}}},
       {0.95F, 0.25F, 0.20F}},
      {{{{Right, Bottom, Back},
         {Left, Bottom, Back},
         {Left, Top, Back},
         {Right, Top, Back}}},
       {0.75F, 0.18F, 0.16F}},
      {{{{Left, Bottom, Back},
         {Left, Bottom, Front},
         {Left, Top, Front},
         {Left, Top, Back}}},
       {0.65F, 0.12F, 0.12F}},
      {{{{Right, Bottom, Front},
         {Right, Bottom, Back},
         {Right, Top, Back},
         {Right, Top, Front}}},
       {0.85F, 0.18F, 0.18F}},
      {{{{Left, Top, Front},
         {Right, Top, Front},
         {Right, Top, Back},
         {Left, Top, Back}}},
       {1.0F, 0.38F, 0.32F}},
      {{{{Left, Bottom, Back},
         {Right, Bottom, Back},
         {Right, Bottom, Front},
         {Left, Bottom, Front}}},
       {0.45F, 0.08F, 0.08F}},
  }};

  glBegin(GL_QUADS);
  for (const Face &face : faces) {
    glColor3f(face.color.r, face.color.g, face.color.b);
    for (const glm::vec3 &vertex : face.vertices) {
      glVertex3f(vertex.x, vertex.y, vertex.z);
    }
  }
  glEnd();
}

float rotationDegreesForFacing(const glm::vec3 &facing) {
  return glm::degrees(std::atan2(-facing.x, -facing.z));
}

std::size_t keyIndexBefore(double animationTime,
                           const std::vector<VectorKey> &keys) {
  if (keys.size() <= 1) {
    return 0;
  }

  for (std::size_t index = 0; index + 1 < keys.size(); ++index) {
    if (animationTime < keys[index + 1].time) {
      return index;
    }
  }
  return keys.size() - 2;
}

std::size_t keyIndexBefore(double animationTime,
                           const std::vector<QuaternionKey> &keys) {
  if (keys.size() <= 1) {
    return 0;
  }

  for (std::size_t index = 0; index + 1 < keys.size(); ++index) {
    if (animationTime < keys[index + 1].time) {
      return index;
    }
  }
  return keys.size() - 2;
}

float interpolationFactor(double animationTime, double startTime,
                          double endTime) {
  const double duration = endTime - startTime;
  if (duration <= std::numeric_limits<double>::epsilon()) {
    return 0.0F;
  }
  return static_cast<float>((animationTime - startTime) / duration);
}

glm::vec3 sampleVectorKeys(double animationTime,
                           const std::vector<VectorKey> &keys,
                           const glm::vec3 &fallback) {
  if (keys.empty()) {
    return fallback;
  }
  if (keys.size() == 1) {
    return keys.front().value;
  }

  const std::size_t keyIndex = keyIndexBefore(animationTime, keys);
  const VectorKey &currentKey = keys[keyIndex];
  const VectorKey &nextKey = keys[keyIndex + 1];
  return glm::mix(
      currentKey.value, nextKey.value,
      interpolationFactor(animationTime, currentKey.time, nextKey.time));
}

glm::quat sampleQuaternionKeys(double animationTime,
                               const std::vector<QuaternionKey> &keys,
                               const glm::quat &fallback) {
  if (keys.empty()) {
    return fallback;
  }
  if (keys.size() == 1) {
    return glm::normalize(keys.front().value);
  }

  const std::size_t keyIndex = keyIndexBefore(animationTime, keys);
  const QuaternionKey &currentKey = keys[keyIndex];
  const QuaternionKey &nextKey = keys[keyIndex + 1];
  return glm::normalize(glm::slerp(
      currentKey.value, nextKey.value,
      interpolationFactor(animationTime, currentKey.time, nextKey.time)));
}

double firstAnimationKeyTime(const AnimationChannel &channel) {
  double firstTime = std::numeric_limits<double>::infinity();
  if (!channel.positions.empty()) {
    firstTime = std::min(firstTime, channel.positions.front().time);
  }
  if (!channel.rotations.empty()) {
    firstTime = std::min(firstTime, channel.rotations.front().time);
  }
  if (!channel.scales.empty()) {
    firstTime = std::min(firstTime, channel.scales.front().time);
  }
  return std::isfinite(firstTime) ? firstTime : 0.0;
}

struct TransformComponents {
  glm::vec3 position{0.0F, 0.0F, 0.0F};
  glm::quat rotation{1.0F, 0.0F, 0.0F, 0.0F};
  glm::vec3 scale{1.0F, 1.0F, 1.0F};
};

glm::mat4 composeTransform(const TransformComponents &transform) {
  return glm::translate(glm::mat4{1.0F}, transform.position) *
         glm::mat4_cast(transform.rotation) *
         glm::scale(glm::mat4{1.0F}, transform.scale);
}

TransformComponents decomposeTransform(const glm::mat4 &transform) {
  TransformComponents result;
  result.position = glm::vec3{transform[3]};
  result.scale = {glm::length(glm::vec3{transform[0]}),
                  glm::length(glm::vec3{transform[1]}),
                  glm::length(glm::vec3{transform[2]})};

  glm::mat3 rotationMatrix{1.0F};
  if (result.scale.x > std::numeric_limits<float>::epsilon()) {
    rotationMatrix[0] = glm::vec3{transform[0]} / result.scale.x;
  }
  if (result.scale.y > std::numeric_limits<float>::epsilon()) {
    rotationMatrix[1] = glm::vec3{transform[1]} / result.scale.y;
  }
  if (result.scale.z > std::numeric_limits<float>::epsilon()) {
    rotationMatrix[2] = glm::vec3{transform[2]} / result.scale.z;
  }
  result.rotation = glm::normalize(glm::quat_cast(rotationMatrix));
  return result;
}

glm::mat4 nodeTransformForAnimation(const SkeletonNode &node,
                                    const AnimationClip &animation,
                                    double animationTime) {
  const auto channelIterator = animation.channelIndexByNodeName.find(node.name);
  if (channelIterator == animation.channelIndexByNodeName.end()) {
    return node.transform;
  }

  const AnimationChannel &channel = animation.channels[channelIterator->second];
  const TransformComponents bindTransform = decomposeTransform(node.transform);
  const glm::vec3 position = sampleVectorKeys(animationTime, channel.positions,
                                              bindTransform.position);
  const glm::quat rotation = sampleQuaternionKeys(
      animationTime, channel.rotations, bindTransform.rotation);
  const glm::vec3 scale =
      sampleVectorKeys(animationTime, channel.scales, bindTransform.scale);
  const glm::mat4 sampledTransform =
      composeTransform(TransformComponents{position, rotation, scale});

  if (!animation.retargetFirstFrameToBindPose) {
    return sampledTransform;
  }

  const double referenceTime = firstAnimationKeyTime(channel);
  const glm::quat referenceRotation = sampleQuaternionKeys(
      referenceTime, channel.rotations, bindTransform.rotation);

  if (animation.keepBindPoseTranslations) {
    const glm::quat retargetedRotation =
        bindTransform.rotation * glm::inverse(referenceRotation) * rotation;
    return composeTransform(TransformComponents{
        bindTransform.position, retargetedRotation, bindTransform.scale});
  }

  const glm::vec3 referencePosition = sampleVectorKeys(
      referenceTime, channel.positions, bindTransform.position);
  const glm::vec3 referenceScale =
      sampleVectorKeys(referenceTime, channel.scales, bindTransform.scale);
  const glm::mat4 referenceTransform = composeTransform(TransformComponents{
      referencePosition, referenceRotation, referenceScale});

  return node.transform * glm::inverse(referenceTransform) * sampledTransform;
}

void computeBoneMatricesRecursive(const SkeletonNode &node,
                                  const glm::mat4 &parentTransform,
                                  const Model &model,
                                  const AnimationClip &animation,
                                  double animationTime,
                                  std::vector<glm::mat4> &boneMatrices) {
  const glm::mat4 globalTransform =
      parentTransform *
      nodeTransformForAnimation(node, animation, animationTime);

  const auto boneIterator = model.boneIndexByName.find(node.name);
  if (boneIterator != model.boneIndexByName.end()) {
    const int boneIndex = boneIterator->second;
    boneMatrices[boneIndex] = model.globalInverseTransform * globalTransform *
                              model.bones[boneIndex].offsetMatrix;
  }

  for (const SkeletonNode &child : node.children) {
    computeBoneMatricesRecursive(child, globalTransform, model, animation,
                                 animationTime, boneMatrices);
  }
}

std::vector<glm::mat4> computeBoneMatrices(const Model &model,
                                           const AnimationClip &animation,
                                           float elapsedSeconds) {
  std::vector<glm::mat4> boneMatrices(model.bones.size(), glm::mat4{1.0F});
  if (!model.hasSkeleton() || !animation.isLoaded()) {
    return boneMatrices;
  }

  const double ticksPerSecond =
      animation.ticksPerSecond > 0.0 ? animation.ticksPerSecond : 24.0;
  const double timeInTicks =
      static_cast<double>(elapsedSeconds) * ticksPerSecond;
  const double animationTime = std::fmod(timeInTicks, animation.durationTicks);
  computeBoneMatricesRecursive(model.rootNode, glm::mat4{1.0F}, model,
                               animation, animationTime, boneMatrices);
  return boneMatrices;
}

Vertex animatedVertex(const Vertex &vertex,
                      const std::vector<glm::mat4> &boneMatrices) {
  Vertex result = vertex;

  glm::vec4 skinnedPosition{0.0F, 0.0F, 0.0F, 0.0F};
  glm::vec3 skinnedNormal{0.0F, 0.0F, 0.0F};
  float totalWeight = 0.0F;
  for (int slot = 0; slot < MaxVertexBones; ++slot) {
    const int boneId = vertex.boneIds[slot];
    const float weight = vertex.boneWeights[slot];
    if (boneId < 0 || boneId >= static_cast<int>(boneMatrices.size()) ||
        weight <= 0.0F) {
      continue;
    }

    const glm::mat4 &boneMatrix = boneMatrices[boneId];
    skinnedPosition += boneMatrix * glm::vec4{vertex.position, 1.0F} * weight;
    skinnedNormal += glm::mat3(boneMatrix) * vertex.normal * weight;
    totalWeight += weight;
  }

  if (totalWeight > std::numeric_limits<float>::epsilon()) {
    result.staticPosition = glm::vec3{skinnedPosition};
    result.staticNormal = glm::normalize(skinnedNormal);
  }
  return result;
}

void drawModel(const Model &model, const AnimationClip &animation,
               float animationTime, const Texture2D &texture) {
  const std::vector<glm::mat4> boneMatrices =
      computeBoneMatrices(model, animation, animationTime);

  if (texture.isLoaded()) {
    glEnable(GL_TEXTURE_2D);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_ALPHA_TEST);
    glAlphaFunc(GL_GREATER, 0.01F);
    glBindTexture(GL_TEXTURE_2D, texture.id);
    glColor4f(1.0F, 1.0F, 1.0F, 1.0F);
  } else {
    glDisable(GL_TEXTURE_2D);
    glColor3f(0.82F, 0.76F, 0.65F);
  }

  glBegin(GL_TRIANGLES);
  for (const Mesh &mesh : model.meshes) {
    for (const unsigned int index : mesh.indices) {
      if (index >= mesh.vertices.size()) {
        continue;
      }

      const Vertex vertex =
          mesh.isSkinned ? animatedVertex(mesh.vertices[index], boneMatrices)
                         : mesh.vertices[index];
      glNormal3f(vertex.staticNormal.x, vertex.staticNormal.y,
                 vertex.staticNormal.z);
      glTexCoord2f(vertex.texCoord.x, vertex.texCoord.y);
      glVertex3f(vertex.staticPosition.x, vertex.staticPosition.y,
                 vertex.staticPosition.z);
    }
  }
  glEnd();
  if (texture.isLoaded()) {
    glBindTexture(GL_TEXTURE_2D, 0);
    glDisable(GL_ALPHA_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_TEXTURE_2D);
  }
}

void configureOpenGl() {
  glEnable(GL_DEPTH_TEST);
  glDisable(GL_CULL_FACE);
  glDisable(GL_BLEND);
  glDisable(GL_ALPHA_TEST);
  glClearColor(0.48F, 0.72F, 1.0F, 1.0F);
}

const AnimationClip &
activeAnimationForCharacter(const Character &character,
                            const AnimationClip &idleAnimation,
                            const AnimationClip &idleToWalkAnimation,
                            const AnimationClip &walkAnimation,
                            const AnimationClip &walkToStopAnimation) {
  switch (character.animationState) {
  case CharacterAnimationState::Idle:
    return idleAnimation;
  case CharacterAnimationState::IdleToWalk:
    return idleToWalkAnimation.isLoaded() ? idleToWalkAnimation : walkAnimation;
  case CharacterAnimationState::Walk:
    return walkAnimation;
  case CharacterAnimationState::WalkToStop:
    return walkToStopAnimation.isLoaded() ? walkToStopAnimation : idleAnimation;
  }

  return idleAnimation;
}

void renderScene(const Camera &camera, const Character &character,
                 const Model &bodyModel, const Texture2D &bodyTexture,
                 const AnimationClip &activeAnimation, int framebufferWidth,
                 int framebufferHeight) {
  glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

  const float aspectRatio = framebufferHeight > 0
                                ? static_cast<float>(framebufferWidth) /
                                      static_cast<float>(framebufferHeight)
                                : 1.0F;
  const glm::mat4 projection = glm::perspective(
      glm::radians(FieldOfView), aspectRatio, NearPlane, FarPlane);

  loadMatrix(GL_PROJECTION, projection);
  loadMatrix(GL_MODELVIEW, camera.viewMatrix());

  drawGroundGrid();

  glPushMatrix();
  glTranslatef(character.position.x, character.position.y,
               character.position.z);
  glRotatef(rotationDegreesForFacing(character.facing), 0.0F, 1.0F, 0.0F);
  if (bodyModel.isLoaded()) {
    glScalef(0.01F, 0.01F, 0.01F);
    drawModel(bodyModel, activeAnimation, character.animationTime, bodyTexture);
  } else {
    drawCube();
  }
  glPopMatrix();
}

GLFWwindow *createWindow() {
  glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 2);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 1);
  glfwWindowHint(GLFW_RESIZABLE, GLFW_TRUE);

  GLFWwindow *window = glfwCreateWindow(WindowWidth, WindowHeight,
                                        "Project Zomboid C++ Engine Prototype",
                                        nullptr, nullptr);
  if (window == nullptr) {
    std::cerr << "Failed to create a GLFW window.\n";
    return nullptr;
  }

  glfwMakeContextCurrent(window);
  glfwSwapInterval(1);
  glfwSetFramebufferSizeCallback(window, framebufferSizeCallback);
  glfwSetInputMode(window, GLFW_CURSOR, GLFW_CURSOR_NORMAL);
  return window;
}
} // namespace

int main() {
  glfwSetErrorCallback(errorCallback);
  if (glfwInit() != GLFW_TRUE) {
    std::cerr << "Failed to initialize GLFW.\n";
    return EXIT_FAILURE;
  }

  GLFWwindow *window = createWindow();
  if (window == nullptr) {
    glfwTerminate();
    return EXIT_FAILURE;
  }

  InputState input;
  glfwSetWindowUserPointer(window, &input);
  glfwSetScrollCallback(window, scrollCallback);

  const Model bodyModel = loadModel(BodyModelPath);
  const Texture2D bodyTexture = loadTexture2D(BodyTexturePath);
  const AnimationClip idleAnimation =
      loadAnimationClip(IdleAnimationPath, "Bob_Idle");
  const AnimationClip idleToWalkAnimation =
      loadAnimationClip(IdleToWalkAnimationPath, "Bob_IdleToWalk", true, true);
  const AnimationClip walkAnimation =
      loadAnimationClip(WalkAnimationPath, "Bob_Walk", true, true);
  const AnimationClip walkToStopAnimation =
      loadAnimationClip(WalkToStopAnimationPath, "Bob_WalkToStop", true, true);
  printAnimationMatchReport(bodyModel, idleAnimation);
  printAnimationMatchReport(bodyModel, idleToWalkAnimation);
  printAnimationMatchReport(bodyModel, walkAnimation);
  printAnimationMatchReport(bodyModel, walkToStopAnimation);
  configureOpenGl();

  float previousTime = static_cast<float>(glfwGetTime());
  while (glfwWindowShouldClose(window) == GLFW_FALSE) {
    const float currentTime = static_cast<float>(glfwGetTime());
    const float deltaTime = currentTime - previousTime;
    previousTime = currentTime;

    processKeyboard(window, input, deltaTime, idleToWalkAnimation,
                    walkToStopAnimation);

    int framebufferWidth = 0;
    int framebufferHeight = 0;
    glfwGetFramebufferSize(window, &framebufferWidth, &framebufferHeight);
    const AnimationClip &activeAnimation = activeAnimationForCharacter(
        input.character, idleAnimation, idleToWalkAnimation, walkAnimation,
        walkToStopAnimation);
    renderScene(input.camera, input.character, bodyModel, bodyTexture,
                activeAnimation, framebufferWidth, framebufferHeight);

    glfwSwapBuffers(window);
    glfwPollEvents();
  }

  glfwDestroyWindow(window);
  glfwTerminate();
  return EXIT_SUCCESS;
}
