#include <GLFW/glfw3.h>

#include <assimp/Importer.hpp>
#include <assimp/matrix4x4.h>
#include <assimp/postprocess.h>
#include <assimp/scene.h>

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <utility>
#include <vector>

namespace {
constexpr int WindowWidth = 1280;
constexpr int WindowHeight = 720;
constexpr float CharacterMoveSpeed = 4.0F;
constexpr float ZoomSpeed = 1.25F;
constexpr float MinCameraDistance = 4.0F;
constexpr float MaxCameraDistance = 40.0F;
constexpr float FieldOfView = 45.0F;
constexpr float NearPlane = 0.1F;
constexpr float FarPlane = 200.0F;
constexpr const char* ManModelPath = "media/man_model.fbx";

struct Vertex {
    glm::vec3 position{};
    glm::vec3 normal{0.0F, 1.0F, 0.0F};
};

struct Mesh {
    std::vector<Vertex> vertices;
    std::vector<unsigned int> indices;
};

struct Model {
    std::vector<Mesh> meshes;
    unsigned int animationCount = 0;

    [[nodiscard]] bool isLoaded() const {
        return !meshes.empty();
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
        distance = std::clamp(distance - amount * ZoomSpeed, MinCameraDistance, MaxCameraDistance);
    }
};

struct Character {
    glm::vec3 position{0.0F, 0.0F, 0.0F};
    glm::vec3 facing{0.0F, 0.0F, -1.0F};
    float animationTime = 0.0F;
    bool isMoving = false;
};

struct InputState {
    Camera camera;
    Character character;
};

glm::mat4 toGlm(const aiMatrix4x4& matrix) {
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

void appendMesh(const aiMesh& assimpMesh, const glm::mat4& transform, Model& model) {
    Mesh mesh;
    mesh.vertices.reserve(assimpMesh.mNumVertices);

    const glm::mat3 normalMatrix = glm::transpose(glm::inverse(glm::mat3(transform)));
    for (unsigned int vertexIndex = 0; vertexIndex < assimpMesh.mNumVertices; ++vertexIndex) {
        const aiVector3D& sourcePosition = assimpMesh.mVertices[vertexIndex];
        const glm::vec4 transformedPosition = transform * glm::vec4{sourcePosition.x, sourcePosition.y, sourcePosition.z, 1.0F};

        glm::vec3 normal{0.0F, 1.0F, 0.0F};
        if (assimpMesh.HasNormals()) {
            const aiVector3D& sourceNormal = assimpMesh.mNormals[vertexIndex];
            normal = glm::normalize(normalMatrix * glm::vec3{sourceNormal.x, sourceNormal.y, sourceNormal.z});
        }

        mesh.vertices.push_back(Vertex{glm::vec3{transformedPosition}, normal});
    }

    for (unsigned int faceIndex = 0; faceIndex < assimpMesh.mNumFaces; ++faceIndex) {
        const aiFace& face = assimpMesh.mFaces[faceIndex];
        if (face.mNumIndices != 3) {
            continue;
        }

        mesh.indices.push_back(face.mIndices[0]);
        mesh.indices.push_back(face.mIndices[1]);
        mesh.indices.push_back(face.mIndices[2]);
    }

    if (!mesh.vertices.empty() && !mesh.indices.empty()) {
        model.meshes.push_back(std::move(mesh));
    }
}

void appendNodeMeshes(const aiScene& scene, const aiNode& node, const glm::mat4& parentTransform, Model& model) {
    const glm::mat4 transform = parentTransform * toGlm(node.mTransformation);

    for (unsigned int meshIndex = 0; meshIndex < node.mNumMeshes; ++meshIndex) {
        const unsigned int sceneMeshIndex = node.mMeshes[meshIndex];
        if (sceneMeshIndex < scene.mNumMeshes) {
            appendMesh(*scene.mMeshes[sceneMeshIndex], transform, model);
        }
    }

    for (unsigned int childIndex = 0; childIndex < node.mNumChildren; ++childIndex) {
        appendNodeMeshes(scene, *node.mChildren[childIndex], transform, model);
    }
}

Model loadModel(const std::filesystem::path& path) {
    Model model;
    if (!std::filesystem::exists(path)) {
        std::cerr << "Model file was not found: " << path << "\n";
        return model;
    }

    Assimp::Importer importer;
    const aiScene* scene = importer.ReadFile(
        path.string(),
        aiProcess_Triangulate | aiProcess_JoinIdenticalVertices | aiProcess_GenSmoothNormals | aiProcess_ImproveCacheLocality);

    if (scene == nullptr || scene->mRootNode == nullptr) {
        std::cerr << "Failed to load model " << path << ": " << importer.GetErrorString() << "\n";
        return model;
    }

    model.animationCount = scene->mNumAnimations;
    appendNodeMeshes(*scene, *scene->mRootNode, glm::mat4{1.0F}, model);

    std::cout << "Loaded " << path << " with " << model.meshes.size() << " mesh(es) and " << model.animationCount
              << " animation(s).\n";
    return model;
}

void errorCallback(int error, const char* description) {
    std::cerr << "GLFW error " << error << ": " << description << '\n';
}

void framebufferSizeCallback(GLFWwindow*, int width, int height) {
    glViewport(0, 0, width, height);
}

void scrollCallback(GLFWwindow* window, double, double yOffset) {
    auto* input = static_cast<InputState*>(glfwGetWindowUserPointer(window));
    if (input == nullptr) {
        return;
    }

    input->camera.zoom(static_cast<float>(yOffset));
}

void processKeyboard(GLFWwindow* window, InputState& input, float deltaTime) {
    if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS) {
        glfwSetWindowShouldClose(window, GLFW_TRUE);
    }

    glm::vec3 movement{0.0F, 0.0F, 0.0F};
    if (glfwGetKey(window, GLFW_KEY_W) == GLFW_PRESS) {
        movement.z -= 1.0F;
    }
    if (glfwGetKey(window, GLFW_KEY_S) == GLFW_PRESS) {
        movement.z += 1.0F;
    }
    if (glfwGetKey(window, GLFW_KEY_D) == GLFW_PRESS) {
        movement.x += 1.0F;
    }
    if (glfwGetKey(window, GLFW_KEY_A) == GLFW_PRESS) {
        movement.x -= 1.0F;
    }

    input.character.isMoving = glm::length(movement) > 0.0F;
    if (input.character.isMoving) {
        const glm::vec3 direction = glm::normalize(movement);
        input.character.position += direction * CharacterMoveSpeed * deltaTime;
        input.character.facing = direction;
        input.character.animationTime += deltaTime;
    } else {
        input.character.animationTime = 0.0F;
    }

    input.camera.target = input.character.position;
}

void loadMatrix(GLenum matrixMode, const glm::mat4& matrix) {
    glMatrixMode(matrixMode);
    glLoadMatrixf(glm::value_ptr(matrix));
}

void drawGroundGrid() {
    constexpr int GridHalfSize = 20;
    glColor3f(0.28F, 0.42F, 0.24F);
    glBegin(GL_LINES);
    for (int line = -GridHalfSize; line <= GridHalfSize; ++line) {
        glVertex3f(static_cast<float>(line), 0.0F, static_cast<float>(-GridHalfSize));
        glVertex3f(static_cast<float>(line), 0.0F, static_cast<float>(GridHalfSize));
        glVertex3f(static_cast<float>(-GridHalfSize), 0.0F, static_cast<float>(line));
        glVertex3f(static_cast<float>(GridHalfSize), 0.0F, static_cast<float>(line));
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
        {{{{Left, Bottom, Front}, {Right, Bottom, Front}, {Right, Top, Front}, {Left, Top, Front}}}, {0.95F, 0.25F, 0.20F}},
        {{{{Right, Bottom, Back}, {Left, Bottom, Back}, {Left, Top, Back}, {Right, Top, Back}}}, {0.75F, 0.18F, 0.16F}},
        {{{{Left, Bottom, Back}, {Left, Bottom, Front}, {Left, Top, Front}, {Left, Top, Back}}}, {0.65F, 0.12F, 0.12F}},
        {{{{Right, Bottom, Front}, {Right, Bottom, Back}, {Right, Top, Back}, {Right, Top, Front}}}, {0.85F, 0.18F, 0.18F}},
        {{{{Left, Top, Front}, {Right, Top, Front}, {Right, Top, Back}, {Left, Top, Back}}}, {1.0F, 0.38F, 0.32F}},
        {{{{Left, Bottom, Back}, {Right, Bottom, Back}, {Right, Bottom, Front}, {Left, Bottom, Front}}}, {0.45F, 0.08F, 0.08F}},
    }};

    glBegin(GL_QUADS);
    for (const Face& face : faces) {
        glColor3f(face.color.r, face.color.g, face.color.b);
        for (const glm::vec3& vertex : face.vertices) {
            glVertex3f(vertex.x, vertex.y, vertex.z);
        }
    }
    glEnd();
}

float rotationDegreesForFacing(const glm::vec3& facing) {
    return glm::degrees(std::atan2(facing.x, facing.z));
}

float walkBobOffset(const Character& character, const Model& model) {
    if (!character.isMoving || model.animationCount == 0) {
        return 0.0F;
    }

    return std::sin(character.animationTime * 12.0F) * 0.08F;
}

void drawModel(const Model& model) {
    glColor3f(0.82F, 0.76F, 0.65F);
    glBegin(GL_TRIANGLES);
    for (const Mesh& mesh : model.meshes) {
        for (const unsigned int index : mesh.indices) {
            if (index >= mesh.vertices.size()) {
                continue;
            }

            const Vertex& vertex = mesh.vertices[index];
            glNormal3f(vertex.normal.x, vertex.normal.y, vertex.normal.z);
            glVertex3f(vertex.position.x, vertex.position.y, vertex.position.z);
        }
    }
    glEnd();
}

void configureOpenGl() {
    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glClearColor(0.48F, 0.72F, 1.0F, 1.0F);
}

void renderScene(const Camera& camera, const Character& character, const Model& manModel, int framebufferWidth, int framebufferHeight) {
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    const float aspectRatio = framebufferHeight > 0
        ? static_cast<float>(framebufferWidth) / static_cast<float>(framebufferHeight)
        : 1.0F;
    const glm::mat4 projection = glm::perspective(glm::radians(FieldOfView), aspectRatio, NearPlane, FarPlane);

    loadMatrix(GL_PROJECTION, projection);
    loadMatrix(GL_MODELVIEW, camera.viewMatrix());

    drawGroundGrid();

    glPushMatrix();
    glTranslatef(character.position.x, character.position.y + walkBobOffset(character, manModel), character.position.z);
    glRotatef(rotationDegreesForFacing(character.facing), 0.0F, 1.0F, 0.0F);
    if (manModel.isLoaded()) {
        glScalef(0.01F, 0.01F, 0.01F);
        drawModel(manModel);
    } else {
        drawCube();
    }
    glPopMatrix();
}

GLFWwindow* createWindow() {
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 2);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 1);
    glfwWindowHint(GLFW_RESIZABLE, GLFW_TRUE);

    GLFWwindow* window = glfwCreateWindow(WindowWidth, WindowHeight, "Project Zomboid C++ Engine Prototype", nullptr, nullptr);
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

    GLFWwindow* window = createWindow();
    if (window == nullptr) {
        glfwTerminate();
        return EXIT_FAILURE;
    }

    InputState input;
    glfwSetWindowUserPointer(window, &input);
    glfwSetScrollCallback(window, scrollCallback);

    const Model manModel = loadModel(ManModelPath);
    configureOpenGl();

    float previousTime = static_cast<float>(glfwGetTime());
    while (glfwWindowShouldClose(window) == GLFW_FALSE) {
        const float currentTime = static_cast<float>(glfwGetTime());
        const float deltaTime = currentTime - previousTime;
        previousTime = currentTime;

        processKeyboard(window, input, deltaTime);

        int framebufferWidth = 0;
        int framebufferHeight = 0;
        glfwGetFramebufferSize(window, &framebufferWidth, &framebufferHeight);
        renderScene(input.camera, input.character, manModel, framebufferWidth, framebufferHeight);

        glfwSwapBuffers(window);
        glfwPollEvents();
    }

    glfwDestroyWindow(window);
    glfwTerminate();
    return EXIT_SUCCESS;
}
