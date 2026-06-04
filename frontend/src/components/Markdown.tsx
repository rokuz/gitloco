import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Render comment bodies as GitHub-flavored markdown. react-markdown does not
 * render raw HTML, so this is safe against injection. Links open in a new tab.
 * Styling is scoped via the `.gitloco-md` class (see diff.css).
 */
export function Markdown({ children }: { children: string }) {
  return (
    <div className="gitloco-md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
