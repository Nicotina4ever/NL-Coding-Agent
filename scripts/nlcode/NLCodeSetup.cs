using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;

internal static class NLCodeSetup
{
    private const string Version = "__VERSION__";
    private const string ReleaseTag = "__RELEASE_TAG__";
    private const string ExpectedZipSha256 = "__ZIP_SHA256__";
    private const string ZipName = "NL-Code-Portable.zip";
    private const string ReleaseUrl =
        "https://github.com/Nicotina4ever/NL-Coding-Agent/releases/download/" + ReleaseTag + "/" + ZipName;

    private static int Main(string[] args)
    {
        bool silent = false, noShortcuts = false, force = false;
        string from = null, installDir = null;
        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            if (arg == "--silent") silent = true;
            else if (arg == "--no-shortcuts") noShortcuts = true;
            else if (arg == "--force") force = true;
            else if (arg == "--from" && i + 1 < args.Length) from = args[++i];
            else if (arg == "--install-dir" && i + 1 < args.Length) installDir = args[++i];
        }
        try
        {
            string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            if (string.IsNullOrEmpty(root)) root = Directory.GetCurrentDirectory();
            if (string.IsNullOrEmpty(installDir))
            {
                installDir = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "Programs", "NL Code");
            }
            installDir = Path.GetFullPath(installDir);
            string zip = from;
            if (string.IsNullOrEmpty(zip))
            {
                string adjacent = Path.Combine(root, ZipName);
                if (File.Exists(adjacent)) zip = adjacent;
            }
            string work = Path.Combine(Path.GetTempPath(), "NLCodeSetup-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(work);
            try
            {
                if (string.IsNullOrEmpty(zip))
                {
                    zip = Path.Combine(work, ZipName);
                    Download(zip);
                }
                if (!File.Exists(zip)) throw new FileNotFoundException("Portable package not found.", zip);
                Verify(zip);
                if (Directory.Exists(installDir) && force)
                {
                    Directory.Delete(installDir, true);
                }
                Directory.CreateDirectory(installDir);
                ExtractZip(zip, installDir);
                if (!noShortcuts) CreateShortcuts(installDir);
                string marker = Path.Combine(installDir, "setup-version.txt");
                File.WriteAllText(marker, "NL Code " + Version + Environment.NewLine);
                if (!silent) MessageBox.Show("NL Code " + Version + " installed." + Environment.NewLine + installDir,
                    "NL Code Setup", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 0;
            }
            finally
            {
                try { if (Directory.Exists(work)) Directory.Delete(work, true); } catch { }
            }
        }
        catch (Exception error)
        {
            string log = Path.Combine(Path.GetTempPath(), "NLCodeSetup.log");
            try { File.AppendAllText(log, DateTime.Now.ToString("o") + " ERROR " + error + Environment.NewLine); } catch { }
            if (!silent) MessageBox.Show(error.Message, "NL Code Setup", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    private static void Download(string destination)
    {
        string release = Environment.GetEnvironmentVariable("NLCODE_RELEASE_URL");
        string url = string.IsNullOrWhiteSpace(release) ? ReleaseUrl : release.TrimEnd('/') + "/" + ZipName;
        using (var client = new HttpClient())
        {
            client.Timeout = TimeSpan.FromMinutes(60);
            using (var response = client.GetAsync(url, HttpCompletionOption.ResponseHeadersRead).Result)
            {
                response.EnsureSuccessStatusCode();
                using (var input = response.Content.ReadAsStreamAsync().Result)
                using (var output = File.Create(destination))
                {
                    input.CopyTo(output);
                }
            }
        }
    }

    private static void Verify(string zip)
    {
        string expected = ExpectedZipSha256;
        if (string.IsNullOrWhiteSpace(expected) || expected.StartsWith("__")) return;
        using (var sha = SHA256.Create())
        using (var stream = File.OpenRead(zip))
        {
            string actual = BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
            if (!string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException("Downloaded package checksum does not match this installer.");
            }
        }
    }

    private static string Long(string path)
    {
        string full = Path.GetFullPath(path);
        if (full.StartsWith(@"\\?\")) return full;
        return full.StartsWith(@"\\") ? @"\\?\UNC\" + full.Substring(2) : @"\\?\" + full;
    }

    private static void ExtractZip(string zip, string destination)
    {
        // Code - OSS contains paths over MAX_PATH. Windows' bundled bsdtar extracts
        // them reliably; .NET Framework ZipFile rejects them on this runtime.
        string tar = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "tar.exe");
        if (!File.Exists(tar)) throw new FileNotFoundException("Windows tar.exe is required to extract the package.", tar);
        var start = new ProcessStartInfo(tar)
        {
            UseShellExecute = false,
            RedirectStandardError = true,
            CreateNoWindow = true,
            Arguments = "-xf \"" + zip + "\" -C \"" + destination + "\""
        };
        using (var process = Process.Start(start))
        {
            string error = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
            {
                throw new InvalidDataException("Package extraction failed (tar exit " + process.ExitCode + "): " + error);
            }
        }
    }

    private static void LegacyExtractZip(string zip, string destination)
    {
        // Code - OSS contains paths over MAX_PATH; .NET Framework ZipFile refuses them,
        // so entries are extracted explicitly through the \\?\ long-path namespace.
        using (var archive = ZipFile.OpenRead(zip))
        {
            string root = Long(destination);
            foreach (var entry in archive.Entries)
            {
                string relative = entry.FullName.Replace('/', Path.DirectorySeparatorChar);
                if (relative.Contains("..")) continue;
                string target = Long(Path.Combine(destination, relative));
                if (entry.FullName.EndsWith("/"))
                {
                    Directory.CreateDirectory(target);
                    continue;
                }
                Directory.CreateDirectory(Long(Path.GetDirectoryName(Path.Combine(destination, relative))));
                using (var input = entry.Open())
                using (var output = new FileStream(target, FileMode.Create, FileAccess.Write, FileShare.None))
                {
                    input.CopyTo(output);
                }
            }
        }
    }

    private static void CopyTree(string source, string destination)
    {
        foreach (string directory in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
        {
            Directory.CreateDirectory(directory.Replace(source, destination));
        }
        foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            File.Copy(file, file.Replace(source, destination), true);
        }
    }

    private static void CreateShortcuts(string installDir)
    {
        string target = Path.Combine(installDir, "NL Code Launcher.exe");
        if (!File.Exists(target)) target = Path.Combine(installDir, "NL Code.exe");
        string icon = Path.Combine(installDir, "NL Code.exe");
        var shell = new object();
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        shell = Activator.CreateInstance(shellType);
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        CreateShortcut(shellType, shell, Path.Combine(desktop, "NL Code.lnk"), target, installDir, icon);
        string programs = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string startDir = Path.Combine(programs, "NL Code");
        Directory.CreateDirectory(startDir);
        CreateShortcut(shellType, shell, Path.Combine(startDir, "NL Code.lnk"), target, installDir, icon);
        CreateShortcut(shellType, shell, Path.Combine(startDir, "Uninstall NL Code.lnk"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"),
            installDir, icon, "/c rmdir /s /q \"" + installDir + "\" & rmdir /s /q \"%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\NL Code\"");
    }

    private static void CreateShortcut(Type shellType, object shell, string path, string target,
        string working, string icon, string arguments = "")
    {
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell,
            new object[] { path });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut,
            new object[] { working });
        shortcutType.InvokeMember("IconLocation", BindingFlags.SetProperty, null, shortcut,
            new object[] { icon + ",0" });
        if (!string.IsNullOrEmpty(arguments))
        {
            shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut,
                new object[] { arguments });
        }
        shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }
}
