using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;

internal static class NLCodeLauncher
{
    private static int Main(string[] args)
    {
        string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        if (string.IsNullOrEmpty(root))
        {
            root = Directory.GetCurrentDirectory();
        }
        string engine = Environment.GetEnvironmentVariable("NLCODE_ENGINE_ROOT");
        if (string.IsNullOrWhiteSpace(engine))
        {
            string info = Path.Combine(root, "BUILD_INFO.json");
            if (File.Exists(info))
            {
                Match match = Regex.Match(File.ReadAllText(info),
                    "\"engineRoot\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])+)\"");
                if (match.Success)
                {
                    engine = Regex.Unescape(match.Groups[1].Value).Replace("\\\\", "\\");
                }
            }
        }
        if (string.IsNullOrWhiteSpace(engine))
        {
            engine = @"K:\AI\NL Coding Agent";
        }
        Environment.SetEnvironmentVariable("NL_ENGINE_ROOT", engine);
        string data = Path.Combine(engine, "data");
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("NL_DATA_DIR")) && Directory.Exists(data))
        {
            Environment.SetEnvironmentVariable("NL_DATA_DIR", data);
        }
        string exe = Path.Combine(root, "NL Code.exe");
        if (!File.Exists(exe))
        {
            Console.Error.WriteLine("[NL Code] NL Code.exe not found next to the launcher.");
            return 3;
        }
        ProcessStartInfo start = new ProcessStartInfo(exe, QuoteArguments(args))
        {
            WorkingDirectory = root,
            UseShellExecute = false
        };
        Process.Start(start);
        return 0;
    }

    private static string QuoteArguments(string[] args)
    {
        if (args == null || args.Length == 0)
        {
            return string.Empty;
        }
        StringBuilder builder = new StringBuilder();
        foreach (string arg in args)
        {
            if (builder.Length > 0)
            {
                builder.Append(' ');
            }
            builder.Append('"').Append((arg ?? string.Empty).Replace("\"", "\\\"")).Append('"');
        }
        return builder.ToString();
    }
}
