// After designing the dashboard in edit mode, click "Copy dashboard state"
// and paste the result over `undefined` below.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const initialState: any = {
  "pages": [
    {
      "id": "page-1",
      "filter": {
        "page": [
          {
            "field": {
              "id": "summary.salary"
            },
            "view": {
              "expanded": true,
              "viewTypeId": "selection"
            }
          },
          {
            "field": {
              "id": "payments.due_date"
            },
            "view": {
              "expanded": true
            }
          }
        ],
        "widget": {}
      },
      "widgetLayout": {
        "0": {
          "xTrack": 2,
          "yTrack": 0,
          "xSpan": 10,
          "ySpan": 25
        }
      },
      "selection": {
        "type": "widget",
        "id": "0"
      },
      "widgets": {
        "0": {
          "type": "grid",
          "dataMapping": {
            "cols": [
              {
                "id": "summary.cycle"
              }
            ]
          },
          "format": {
            "title": {
              "enabled": true,
              "typography": {
                "fontFamily": "Times New Roman, serif",
                "fontSize": 24,
                "fontWeight": "normal",
                "fontStyle": "normal"
              }
            },
            "subtitle": {
              "enabled": true,
              "typography": {
                "fontFamily": "Consolas, monospace",
                "fontSize": 12,
                "fontWeight": "normal",
                "fontStyle": "normal"
              }
            },
            "caption": {
              "enabled": true,
              "typography": {
                "fontFamily": "Consolas, monospace",
                "fontSize": 12,
                "fontWeight": "normal",
                "fontStyle": "normal"
              }
            },
            "widget": {
              "backgroundColor": "rgb(209, 158, 242)",
              "borderRadius": 9,
              "borderEnabled": true,
              "borderWidth": 4,
              "borderColor": "rgba(105, 7, 233, 0.149)"
            }
          },
          "sort": [
            {
              "field": {
                "id": "summary.cycle"
              },
              "direction": "asc"
            }
          ]
        }
      }
    }
  ],
  "selectedPageId": "page-1",
  "version": "3.0.0"
};