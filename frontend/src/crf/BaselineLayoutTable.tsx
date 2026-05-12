import type { CSSProperties } from "react";

import { renderBaselineRegistryField } from "./renderBaselineRegistryFields";
import type { BaselineTableLayoutBlock, RegistryField } from "./types";

const tdStyle: CSSProperties = {
  border: "1px solid #d9d9d9",
  padding: 8,
  verticalAlign: "top",
};

export function BaselineLayoutTable({
  block,
  fieldById,
}: {
  block: BaselineTableLayoutBlock;
  fieldById: Map<string, RegistryField>;
}) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        {block.rows.map((row, ri) => (
          <tr key={ri}>
            {row.cells.map((cell, ci) => {
              const colSpan = cell.colspan;
              const rowSpan = cell.rowspan;
              if (cell.blank) {
                return <td key={ci} style={tdStyle} colSpan={colSpan} rowSpan={rowSpan} />;
              }
              const fid = cell.field_id;
              if (fid) {
                const f = fieldById.get(fid);
                return (
                  <td key={ci} style={tdStyle} colSpan={colSpan} rowSpan={rowSpan}>
                    {f ? renderBaselineRegistryField(f) : null}
                  </td>
                );
              }
              return <td key={ci} style={tdStyle} colSpan={colSpan} rowSpan={rowSpan} />;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
