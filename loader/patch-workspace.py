#!/usr/bin/env python3
"""Small patches to the Eaglercraft 26.2 workspace for mods (run by weave.sh; safe to run twice).

Usage: patch-workspace.py WORKSPACE
- ServiceLoader.findFirst(): registers the donor in loader/teavm-compat with Eaglercraft's JdkMethodInjector.
- Pattern.asPredicate/asMatchPredicate (Eaglercraft's donor): returned null, because the lambda it
  returned doesn't survive being copied into Pattern; now returns a plain class (AppleSkin needs it).
- glfwGetMouseButton(): added to Eaglercraft's GLFW stand-in.
- Arrays.copyOfRange (replace-donor in loader/teavm-compat): pads with zeros past the end, as the JDK
  does, instead of throwing (SnakeYAML relies on it).
- Reader/BufferedReader.transferTo and Writer.nullWriter (and nullReader, nullInputStream,
  nullOutputStream) (donors in loader/teavm-compat), Array.setInt and the other primitive
  setters, and Files.newDirectoryStream(dir, glob), added to Eaglercraft's donors for Array and Files.
- Field.getGenericType and Class.getGenericSuperclass/getGenericInterfaces/getTypeParameters
  (Eaglercraft's donors): ask the loader first, through a hook it registers at startup, so Gson and
  other libraries see LinkedHashMap<String, Foo> and that it is a Map<K, V>, rather than raw types (a map
  of settings objects otherwise loaded as plain maps, and broke with ClassCastException).
- ServerFunctionLibrary: mods' datapack functions (.mcfunction) are compiled right away instead of as
  async tasks the loader then waits on, which the browser's single-threaded server can't do (vanilla
  ships no functions, so Eaglercraft never hit this); a function that fails to compile is logged.
- WebGL2Program: a shader that fails to compile is retried with whole numbers made decimal on the lines
  the compiler complained about (desktop GLSL turns 1 into 1.0 next to a float; the browser's GLSL ES
  doesn't, and mods' shaders such as Impact Frames' rely on it). Shaders that compile are untouched.
- StandaloneTeaVMLinker: classes or methods the browser doesn't have, used by mods, no longer stop the
  build. TeaVM compiles each such spot to throw NoClassDefFoundError/NoSuchMethodError if it runs; the
  build log lists them ("was not found"). Any other compiler error still stops the build.
"""
import os, sys


def patch(path, old, new, what):
    s = open(path).read()
    if new in s:
        return
    if old not in s:
        sys.exit("eagler-modloader: %s changed; check the %s patch" % (os.path.basename(path), what))
    open(path, "w").write(s.replace(old, new, 1))


def append_to_class(path, code, marker, what):
    """Adds code before the class's closing brace (once)."""
    s = open(path).read()
    if marker in s:
        return
    end = s.rstrip().rfind("}")
    if end < 0:
        sys.exit("eagler-modloader: %s changed; check the %s patch" % (os.path.basename(path), what))
    open(path, "w").write(s[:end] + code + s[end:])


def main():
    ws = sys.argv[1]
    inj = os.path.join(ws, "teavm-compat/src/main/java/net/lax1dude/eaglercraft/v1_8/teavmcompat/plugin/JdkMethodInjector.java")
    anchor = '\t\t{ "Base64Inject", "java.util.Base64", false },\n'
    patch(inj, anchor, anchor + '\t\t{ "ServiceLoaderInject", "java.util.ServiceLoader", false },\n'
          '\t\t{ "ReaderInject", "java.io.Reader", false },\n'
          '\t\t{ "BufferedReaderInject", "java.io.BufferedReader", false },\n'
          '\t\t{ "WriterInject", "java.io.Writer", false },\n'
          '\t\t{ "InputStreamInject", "java.io.InputStream", false },\n'
          '\t\t{ "OutputStreamInject", "java.io.OutputStream", false },\n', "ServiceLoader and java.io donors")

    anchor = '\t\t{ "ConcurrentMapInject", "java.util.concurrent.ConcurrentMap" },\n'
    patch(inj, anchor, anchor + '\t\t{ "ArraysInject", "java.util.Arrays" }, // eagler-modloader: copyOfRange past the end\n',
          "Arrays.copyOfRange fix")

    inject = os.path.join(ws, "teavm-compat/src/main/java/net/lax1dude/eaglercraft/v1_8/teavmcompat/inject")
    pi = os.path.join(inject, "PatternInject.java")
    patch(pi, "return input -> ((Pattern) (Object) this).matcher(input).find();",
          "return net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlPatternPredicate.find(this); // eagler-modloader",
          "Pattern.asPredicate fix")
    patch(pi, "return input -> ((Pattern) (Object) this).matcher(input).matches();",
          "return net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlPatternPredicate.matches(this); // eagler-modloader",
          "Pattern.asMatchPredicate fix")
    setters = "".join(
        "\n\tpublic static void set%s(Object array, int index, %s value) { // added by eagler-modloader\n"
        "\t\tjava.lang.reflect.Array.set(array, index, %s.valueOf(value));\n\t}\n" % (n, t, b)
        for n, t, b in [("Boolean", "boolean", "Boolean"), ("Byte", "byte", "Byte"), ("Char", "char", "Character"),
                        ("Short", "short", "Short"), ("Int", "int", "Integer"), ("Long", "long", "Long"),
                        ("Float", "float", "Float"), ("Double", "double", "Double")])
    append_to_class(os.path.join(inject, "ArrayInject.java"), setters, "public static void setInt(", "Array setters")
    patch(os.path.join(inject, "FieldInject.java"), """	public Type getGenericType() {
		return (Type) (Object) getType();
	}""", """	public Type getGenericType() {
		Object t = net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlGenericTypes.fieldType(this); // eagler-modloader
		if (t instanceof Type) return (Type) t;
		return (Type) (Object) getType();
	}""", "Field.getGenericType hook")
    ci = os.path.join(inject, "ClassInject.java")
    patch(ci, """	public Type getGenericSuperclass() {
		return (Type) (Object) getSuperclass();
	}""", """	public Type getGenericSuperclass() {
		Object t = net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlGenericTypes.classTypes(this, 0); // eagler-modloader
		if (t instanceof Type) return (Type) t;
		return (Type) (Object) getSuperclass();
	}""", "Class.getGenericSuperclass hook")
    patch(ci, """	public Type[] getGenericInterfaces() {
""", """	public Type[] getGenericInterfaces() {
		Object t = net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlGenericTypes.classTypes(this, 1); // eagler-modloader
		if (t instanceof Type[]) return (Type[]) t;
""", "Class.getGenericInterfaces hook")
    patch(ci, """	public java.lang.reflect.TypeVariable[] getTypeParameters() {
		return new java.lang.reflect.TypeVariable[0];""", """	public java.lang.reflect.TypeVariable[] getTypeParameters() {
		Object t = net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlGenericTypes.classTypes(this, 2); // eagler-modloader
		if (t instanceof java.lang.reflect.TypeVariable[]) return (java.lang.reflect.TypeVariable[]) t;
		return new java.lang.reflect.TypeVariable[0];""", "Class.getTypeParameters hook")
    append_to_class(os.path.join(inject, "FilesInject.java"),
        "\n\tpublic static java.nio.file.DirectoryStream<Path> newDirectoryStream(Path dir, String glob) throws IOException { // added by eagler-modloader\n"
        "\t\treturn net.lax1dude.eaglercraft.v1_8.teavmcompat.EmlNio.newDirectoryStream(dir, glob);\n\t}\n",
        "newDirectoryStream(Path dir, String glob)", "Files.newDirectoryStream")

    glfw = os.path.join(ws, "platform-teavm/src/main/java/org/lwjgl/glfw/GLFW.java")
    anchor = "\tpublic static String glfwGetKeyName("
    patch(glfw, anchor, "\tpublic static int glfwGetMouseButton(final long window, final int button) {\n"
          "\t\treturn PlatformInput.mouseIsButtonDown(button) ? 1 : 0; // added by eagler-modloader\n\t}\n\n" + anchor,
          "glfwGetMouseButton")

    sfl = os.path.join(ws, "game/src/main/java/net/minecraft/server/ServerFunctionLibrary.java")
    old = """               result.put(id, CompletableFuture.supplyAsync(() -> {
                  List<String> lines = readLines(entry.getValue());
                  return CommandFunction.fromLines(id, this.dispatcher, compilationContext, lines);
               }, taskExecutor));"""
    new = """               // eagler-modloader: compiled right away; the browser's server can't wait on a task
               CompletableFuture<CommandFunction<CommandSourceStack>> compiled = new CompletableFuture<>();
               try {
                  compiled.complete(CommandFunction.fromLines(id, this.dispatcher, compilationContext, readLines(entry.getValue())));
               } catch (Throwable t) {
                  compiled.completeExceptionally(t);
               }
               result.put(id, compiled);"""
    patch(sfl, old, new, "datapack functions")
    # and read each result directly: Eaglercraft's handle() completes its new future later, even on a
    # finished one, so handle(...).join() always stopped the world from loading
    old = """               functionFutures.forEach((id, functionFuture) -> functionFuture.handle((function, throwable) -> {
                  if (throwable != null) {
                     LOGGER.error("Failed to load function {}", id, throwable);
                  } else {
                     newFunctions.put(id, function);
                  }

                  return null;
               }).join());"""
    new = """               functionFutures.forEach((id, functionFuture) -> { // eagler-modloader: no join (see above)
                  if (!functionFuture.isDone()) {
                     LOGGER.error("Function {} was not ready", id);
                     return;
                  }
                  try {
                     newFunctions.put(id, functionFuture.join());
                  } catch (Throwable throwable) {
                     LOGGER.error("Failed to load function {}", id, throwable);
                  }
               });"""
    patch(sfl, old, new, "datapack function results")

    linker = os.path.join(ws, "wasm-toolchain/StandaloneTeaVMLinker.java")
    old = """        if (!result.getProblems().getSevereProblems().isEmpty()) {
            throw new IllegalStateException("TeaVM reported severe problems");
        }"""
    new = """        int missing = 0, other = 0;
        for (var p : result.getProblems().getSevereProblems()) {
            if (String.valueOf(p.getText()).contains("was not found")) missing++; else other++;
        }
        if (missing > 0) {
            System.out.println("[eagler-modloader] " + missing + " uses of classes or methods the browser doesn't have"
                + " (listed above as 'was not found'); that code throws an error if it runs");
        }
        if (other > 0) {
            throw new IllegalStateException("TeaVM reported severe problems");
        }"""
    patch(linker, old, new, "missing-class handling")
    prog = os.path.join(ws, "platform-teavm/src/main/java/net/lax1dude/eaglercraft/v1_8/internal/webgl2/WebGL2Program.java")
    old = """		gl.compileShader(shaderId);
		if (!gl.getShaderParameterb(shaderId, WebGL2Const.GL_COMPILE_STATUS)) {
			String logInfo = gl.getShaderInfoLog(shaderId);"""
    new = """		gl.compileShader(shaderId);
		for (int emlTry = 0; emlTry < 4 && !gl.getShaderParameterb(shaderId, WebGL2Const.GL_COMPILE_STATUS); emlTry++) {
			// eagler-modloader: GLSL ES has no implicit int-to-float conversion; fix the lines it complained about
			String emlFixed = emlFloatLiterals(esSource, gl.getShaderInfoLog(shaderId));
			if (emlFixed == null) break;
			esSource = emlFixed;
			gl.shaderSource(shaderId, esSource);
			gl.compileShader(shaderId);
			if (gl.getShaderParameterb(shaderId, WebGL2Const.GL_COMPILE_STATUS)) {
				System.err.println("eagler-webgl2: " + type.getName() + " shader (" + id + ") compiled after making whole numbers decimal");
			}
		}
		if (!gl.getShaderParameterb(shaderId, WebGL2Const.GL_COMPILE_STATUS)) {
			String logInfo = gl.getShaderInfoLog(shaderId);"""
    patch(prog, old, new, "shader whole-number retry")
    append_to_class(prog, """
	/**
	 * eagler-modloader: desktop GLSL converts int to float implicitly (1 - x), GLSL ES 3.00 doesn't. For each
	 * compiler error about an int, the whole-number literals on that line next to the operator it names
	 * (or all on the line, for a function call or assignment) become float literals; never inside [].
	 * Null if nothing changed.
	 */
	static String emlFloatLiterals(String src, String log) {
		if (log == null) return null;
		String[] lines = src.split("\\n", -1);
		boolean changed = false;
		for (String err : log.split("\\n")) {
			if (err.indexOf("int") < 0) continue;
			int a = err.indexOf("0:");
			if (a < 0) continue;
			int b = err.indexOf(':', a + 2);
			if (b < 0) continue;
			int ln;
			try {
				ln = Integer.parseInt(err.substring(a + 2, b).trim()) - 1;
			} catch (NumberFormatException e) {
				continue;
			}
			if (ln < 0 || ln >= lines.length || lines[ln].trim().startsWith("#")) continue;
			String op = null;
			int q1 = err.indexOf('\\'', b), q2 = q1 < 0 ? -1 : err.indexOf('\\'', q1 + 1);
			if (q1 >= 0 && q2 > q1) op = err.substring(q1 + 1, q2);
			boolean whole = err.indexOf("no matching overloaded function") >= 0 || err.indexOf("cannot convert") >= 0;
			if (!whole && (op == null || op.isEmpty() || "+-*/<>=!".indexOf(op.charAt(0)) < 0)) continue;
			String fixed = emlFloatLine(lines[ln], whole ? null : op);
			if (!fixed.equals(lines[ln])) {
				lines[ln] = fixed;
				changed = true;
			}
		}
		return changed ? String.join("\\n", lines) : null;
	}

	private static boolean emlWordChar(char c) {
		return Character.isLetterOrDigit(c) || c == '_' || c == '.';
	}

	private static String emlFloatLine(String line, String op) {
		StringBuilder out = new StringBuilder(line.length() + 8);
		int depth = 0, n = line.length();
		for (int i = 0; i < n; i++) {
			char c = line.charAt(i);
			if (c == '[') depth++;
			else if (c == ']') depth--;
			if (Character.isDigit(c) && (i == 0 || !emlWordChar(line.charAt(i - 1)))) {
				int j = i;
				while (j < n && Character.isDigit(line.charAt(j))) j++;
				out.append(line, i, j);
				if ((j >= n || !emlWordChar(line.charAt(j))) && depth == 0 && (op == null || emlNextTo(line, i, j, op))) out.append(".0");
				i = j - 1;
				continue;
			}
			out.append(c);
		}
		return out.toString();
	}

	private static boolean emlNextTo(String line, int i, int j, String op) {
		int k = i - 1;
		while (k >= 0 && line.charAt(k) == ' ') k--;
		if (k - op.length() + 1 >= 0 && line.startsWith(op, k - op.length() + 1)) return true;
		k = j;
		while (k < line.length() && line.charAt(k) == ' ') k++;
		return line.startsWith(op, k);
	}
""", "static String emlFloatLiterals(", "shader whole-number helper")
    print("workspace: ServiceLoader.findFirst, Reader.transferTo, Array setters, Files.newDirectoryStream, glfwGetMouseButton,"
          " datapack functions, shader whole numbers; mods' missing classes don't stop the build")


if __name__ == "__main__":
    main()
