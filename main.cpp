#include <GLFW/glfw3.h>

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>

#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>

namespace {
constexpr int WindowWidth = 1280;
constexpr int WindowHeight = 720;
constexpr float MovementSpeed = 8.0F;
constexpr float ZoomSpeed = 1.25F;
constexpr float MinCameraDistance = 4.0F;
constexpr float MaxCameraDistance = 40.0F;
constexpr float FieldOfView = 45.0F;
constexpr float NearPlane = 0.1F;
constexpr float FarPlane = 200.0F;

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

struct InputState {
    Camera camera;
};

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

    const float velocity = MovementSpeed * deltaTime;
    const glm::vec3 forward = input.camera.forward();
    const glm::vec3 flatForward = glm::normalize(glm::vec3{forward.x, 0.0F, forward.z});
    const glm::vec3 right = input.camera.right();

    if (glfwGetKey(window, GLFW_KEY_W) == GLFW_PRESS) {
        input.camera.target += flatForward * velocity;
    }
    if (glfwGetKey(window, GLFW_KEY_S) == GLFW_PRESS) {
        input.camera.target -= flatForward * velocity;
    }
    if (glfwGetKey(window, GLFW_KEY_D) == GLFW_PRESS) {
        input.camera.target += right * velocity;
    }
    if (glfwGetKey(window, GLFW_KEY_A) == GLFW_PRESS) {
        input.camera.target -= right * velocity;
    }
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

void configureOpenGl() {
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_CULL_FACE);
    glCullFace(GL_BACK);
    glClearColor(0.48F, 0.72F, 1.0F, 1.0F);
}

void renderScene(const Camera& camera, int framebufferWidth, int framebufferHeight) {
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    const float aspectRatio = framebufferHeight > 0
        ? static_cast<float>(framebufferWidth) / static_cast<float>(framebufferHeight)
        : 1.0F;
    const glm::mat4 projection = glm::perspective(glm::radians(FieldOfView), aspectRatio, NearPlane, FarPlane);

    loadMatrix(GL_PROJECTION, projection);
    loadMatrix(GL_MODELVIEW, camera.viewMatrix());

    drawGroundGrid();
    drawCube();
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
        renderScene(input.camera, framebufferWidth, framebufferHeight);

        glfwSwapBuffers(window);
        glfwPollEvents();
    }

    glfwDestroyWindow(window);
    glfwTerminate();
    return EXIT_SUCCESS;
}
