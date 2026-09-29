# DevContainer für TicTacTest: Alpine, Java 25, Gradle, Benutzer 1000:1000.
# Wird lokal und als Job-Container in der CI/CD-Pipeline verwendet.
FROM eclipse-temurin:25-jdk-alpine-3.22

LABEL org.opencontainers.image.source="https://github.com/philderks/450-tictactest-mvk"

# bash/git: von GitHub Actions und VS Code vorausgesetzt
# libstdc++: wird vom Alpine-Node des Actions-Runners gebraucht
# github-cli: für den gh-Aufruf im Coverage Gate
# shadow:     erlaubt VS Code, die UID an den Host anzugleichen
RUN apk add --no-cache bash curl git github-cli libstdc++ shadow sudo unzip

# Gleiche Version wie der Wrapper, siehe gradle/wrapper/gradle-wrapper.properties
ARG GRADLE_VERSION=9.7.0
ARG GRADLE_SHA256=84fbba45c7f4c64abc77460e1c00f541e9f960e3c7ed2538f1ede19eacd873ae
RUN curl -fsSL -o /tmp/gradle.zip "https://services.gradle.org/distributions/gradle-${GRADLE_VERSION}-bin.zip" \
	&& echo "${GRADLE_SHA256}  /tmp/gradle.zip" | sha256sum -c - \
	&& unzip -q /tmp/gradle.zip -d /opt \
	&& ln -s "/opt/gradle-${GRADLE_VERSION}/bin/gradle" /usr/local/bin/gradle \
	&& rm /tmp/gradle.zip

RUN addgroup -g 1000 vscode \
	&& adduser -u 1000 -G vscode -s /bin/bash -D vscode \
	&& echo "vscode ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vscode

# JUnit kommt nicht ins Image, sondern über build.gradle als Test-Abhängigkeit.
USER vscode
WORKDIR /workspaces
